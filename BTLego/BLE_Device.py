import asyncio
import uuid
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .Decoder import Decoder

class BLE_Device():
	# 0:	Don't debug
	# 1:	Print weird stuff
	# 2:	Print most of the information flow
	# 3:	Print stuff even you the debugger probably don't need
	DEBUG = 0

	# MESSAGE TYPES ( type, key, value )
	# event:
	#	'button':			'pressed'
	#	'consciousness':	'asleep','awake'
	#	'coincount':		(count_int, last_obtained_via_int)
	#	'power':			'turned_off'
	#	'bt':				'disconnected'
	#	'multiplayer':		('coincount', count), ('double_coincount', count),  ('triple_coincount', count)
	# motion
	#	TODO raw data
	#	TODO gesture
	# scanner
	#	'code':		((5-char string),(int))
	#	'color':	(solid_colors)
	# pants
	#	'pants': (pants_codes)
	# info
	#	'player':		'mario', 'luigi', 'peach'
	#	'icon': 		((app_icon_names),(app_icon_color_names))
	#	'batt':			(percentage)
	#	'power': 		'turning_off', 'disconnecting'
	# voltage:
	#	TODO
	# error
	#	message:	(str)

	message_types = (
		'event',
		'info',
		'error',
	)

	characteristic_uuid = '00001624-1212-efde-1623-785feabcd123'
	hub_service_uuid = '00001623-1212-efde-1623-785feabcd123'

	# populated in __init__

	def __init__(self, advertisement_data=None):

		self.system_type = None
		self.address = None
		self.client = None
		self.connected = False

		# keep around for whatever
		self.device = None
		self.advertisement = None
		self.message_queue = None
		self.callbacks = None

		self.port_data = {
		}

		self.port_mode_info = {
			'port_count':-1,
			'requests_until_complete':0		# Port interrogation
		}

		self.message_queue = SimpleQueue()
		self.drainlock_changes_queue = SimpleQueue()

		# Message type subscriptions reference count
		self.BLE_event_subscriptions = {}

		self.callbacks = {}
		# UUID indexed tuples of...
		# 0: callback function
		# 1: Tuple of message type subscriptions

		self.lock = asyncio.Lock()
		self.drain_lock = asyncio.Lock()

		self._reset_event_subscription_counters()

	def _init_port_data(self, port, port_id):
		self.port_data[port] = {
			'io_type_id':port_id,
			'name':Decoder.io_type_id_str[port_id],
			'status': 0x1	# Decoder.io_event_type_str[0x1]
		}
		self.port_mode_info[port] = {
			'mode_count': -1
		}
		self.port_mode_info['port_count'] += 1

	# Override in subclass and call super if you subclass to initialize BLE_event_subscriptions with all available message types
	def _reset_event_subscription_counters(self):
		for message_type in BLE_Device.message_types:
			self.BLE_event_subscriptions[message_type] = 0;

	async def dump_status(self):
		BLE_Device.dp("EVENT SUBS\n"+json.dumps(self.BLE_event_subscriptions, indent=4))
#		BLE_Device.dp("PORT MODE INFO\n"+json.dumps(self.port_mode_info, indent=4))
#		BLE_Device.dp("PORT DATA\n"+json.dumps(self.port_data, indent=4))
		BLE_Device.dp("CALLBACKS\n"+json.dumps(self.callbacks, indent=4, default=lambda function: '<function callback>'))

	async def connect(self, device, advertisement_data):
		async with self.lock:
			self.system_type = Decoder.determine_device_shortname(advertisement_data)
			BLE_Device.dp("Connecting to "+str(self.system_type)+"...",2)
			self.device = device
			self.advertisement = advertisement_data
			try:
				async with BleakClient(device.address) as self.client:
					if not self.client.is_connected:
						BLE_Device.dp("Failed to connect after client creation")
						return
					BLE_Device.dp("Connected to "+self.system_type+"! ("+str(device.name)+")",2)
					self.message_queue.put(('info','player',self.system_type))
					self.connected = True
					self.address = device.address
					await self.client.start_notify(BLE_Device.characteristic_uuid, self.device_events)
					await asyncio.sleep(0.1)

					# turn on everything everybody registered for
					for event_sub_type,sub_count in self.BLE_event_subscriptions.items():
						if sub_count > 0:
							if not await self._set_hardware_subscription(event_sub_type, True):
								BLE_Device.dp("INVALID Subscription option on connect:"+event_sub_type)

					await self._inital_connect_updates()

					while self.client.is_connected:
						await asyncio.sleep(0.05)
					self.connected = False
					BLE_Device.dp(self.system_type+" has disconnected.",2)

			except Exception as e:
				BLE_Device.dp("Unable to connect to "+str(device.address) + ": "+str(e))

	# Overrideable
	async def _inital_connect_updates(self):
		await self.request_name_update()
		await self.request_version_update()

		# Use as a guaranteed init event
		await self.request_battery_update()

		#await self.interrogate_ports()

	# FIXME: should register the callback an all the subscriptions at once
	# set/unset registrations separately

	async def register_callback(self, callback):
		BLE_Device.dp(f'Registring callback {callback_uuid}',2)
		callback_uuid = str(uuid.uuid4())
		self.drainlock_changes_queue.put(('callback', 'register', (callback_uuid,callback)))

		# Outside of the drain
		if not self.drain_lock.locked():
			async with self.drain_lock:
				await self.__process_drainlock_queue()

		return callback_uuid

	async def unregister_callback(self, callback_uuid):
		self.drainlock_changes_queue.put(('callback', 'unregister', (callback_uuid,)))

		# Outside of the drain
		if not self.drain_lock.locked():
			async with self.drain_lock:
				await self.__process_drainlock_queue()

	# MUST be called within drain_lock
	async def __process_drainlock_queue(self):
		while not self.drainlock_changes_queue.empty():
			change_order = self.drainlock_changes_queue.get()
			parameters = change_order[2]
			if change_order[0] == 'callback':
				if change_order[1] == 'unregister':
					callback_uuid = parameters[0]
					BLE_Device.dp(f'Unregistering callback {callback_uuid}',2)

					if not callback_uuid in self.callbacks:
						BLE_Device.dp(f'Given UUID {callback_uuid} doesn\'t exist to unregister')
						continue

					callback_settings = self.callbacks[callback_uuid]
					current_subscriptions = callback_settings[1]

					if self.connected:
						BLE_Device.dp(f'Unusbscribe processing {callback_uuid}',3)
						for subscription in current_subscriptions:
							self._set_callback_subscriptions(parameters[0], subscription, False)

							if (self.BLE_event_subscriptions[subscription] <= 0):
								await self._set_hardware_subscription(subscription, False)
						BLE_Device.dp(f'Finished processing unsubscribes {callback_uuid}',3)
					else:
						# FIXME: If it reconnects, the messages come back?
						BLE_Device.dp(f'UUID {callback_uuid} requested unsubscribe... but.. the device was not connected?')

					self.callbacks.pop(callback_uuid, None)

				# FIXME: Doesn't actually take the third parameter
				# (callback_uuid,callback,subscription_tuple)
				elif change_order[1] == 'register':
					BLE_Device.dp(f'Registering callback {parameters[0]}',2)
					self.callbacks[parameters[0]] = (parameters[1], ())
				else:
					BLE_Device.dp("Invalid message type "+message_type,0)

			# Caller verifies message_type
			# (callback_uuid, message_type, boolean_subscription)
			elif change_order[0] == 'subscription' and change_order[1] == 'change':
				BLE_Device.dp(f'Requesting {parameters[2]} subscription to {parameters[1]}',2)
				self._set_callback_subscriptions(parameters[0], parameters[1], parameters[2])

				# first subscribing callback: turn on the event	OR last subscribing callback: turn off the subscription
				# Otherwise, don't bother the hardware
				if (self.BLE_event_subscriptions[parameters[1]] <= 0 and parameters[2]) or (self.BLE_event_subscriptions[parameters[1]] == 1 and not parameters[2]):
					if not await self._set_hardware_subscription(parameters[1], parameters[2]):
						BLE_Device.dp("INVALID Subscription option:"+parameters[1])

	def request_update_on_callback(self,update_request):
		# FIXME: User should be able to poke mario for stuff like request_name_update
		pass

	# Hmm... just because this returns true doesn't mean you're going to get the messages (see failure modes in __process_drainlock_queue)
	async def subscribe_to_messages_on_callback(self, callback_uuid, message_type, subscribe=True):
		# Not going to check if the callback is valid here, because it could be on the queue

		# Contains all message_types for the class after _reset_event_subscription_counters() in subclasses
		if not message_type in self.BLE_event_subscriptions:
			BLE_Device.dp("Invalid message type "+message_type)
			return False

		self.drainlock_changes_queue.put(('subscription', 'change', (callback_uuid,message_type,subscribe)))

		# Outside of the drain
		if not self.drain_lock.locked():
			async with self.drain_lock:
				await self.__process_drainlock_queue()

		return True

	# return the tuple of subscriptions that were set
	# Assumes you filtered this to only valid message types
	def _set_callback_subscriptions(self, callback_uuid, message_type, subscribe=True):
		do_nothing = False
		if not callback_uuid in self.callbacks:
			# Could happen with getting deferred in the queue?
			BLE_Device.dp(f'Given UUID {callback_uuid} disappeared.  Failed to subscribe to {message_type}')
			return False

		callback_settings = self.callbacks[callback_uuid]
		current_subscriptions = callback_settings[1]
		new_subscriptions = ()
		if subscribe:
			if message_type in current_subscriptions:
				do_nothing = True
			else:
				new_subscriptions = current_subscriptions+(message_type,)
		else:
			if message_type in current_subscriptions:
				sub_list = list(current_subscriptions)
				sub_list.remove(message_type)
				new_subscriptions = tuple(sub_list)
			else:
				do_nothing = True

		if do_nothing:
			new_subscriptions = current_subscriptions
		else:
			if subscribe:
				self.BLE_event_subscriptions[message_type] += 1
				BLE_Device.dp(f'Setting callback {callback_uuid} subscription to {message_type}',3)
			else:
				self.BLE_event_subscriptions[message_type] -= 1
				BLE_Device.dp(f'Removing callback {callback_uuid} subscription to {message_type}',3)

			self.callbacks[callback_uuid] = (callback_settings[0], new_subscriptions)

		return new_subscriptions

	# Filter for set_BLE_subscription so the subclasses don't have to bother
	def _set_hardware_subscription(self, message_type, should_subscribe=True):
		if not self.connected:
			print(f'Not connected: Can\'t set subscription {message_type} to {should_subscribe}')
			return False

		if not message_type in self.BLE_event_subscriptions:
			print(f'Couldn\'t find {message_type}')
			return False

		return self.set_BLE_subscription(message_type, should_subscribe)

	# True if message_type is processed, false otherwise
	# There's two low level kind of subscriptions, hub property updates and single port update format
	# Override in subclass, call super if you don't process the message type.
	async def set_BLE_subscription(self, message_type, should_subscribe=True):

		valid_sub_name = True

		if message_type == 'event':
			# await self.set_port_subscriptions([[self.EVENTS_PORT,2,5,should_subscribe]])
			await self.set_updates_for_hub_properties([
				['Button',should_subscribe]				# Works as advertised (the "button" is the bluetooth button)
			])

#				elif message_type == 'error'
# You're gonna get these.  Don't know why I even let you choose?

		elif message_type == 'info':
			await self.set_updates_for_hub_properties([
				['Advertising Name',should_subscribe]	# I guess this works different than requesting the update because something else could change it, but then THAT would cause an update message

				# Kind of a problem to implement in the future because you don't want these spewing at you
				# Probably need to be separate types
				#['RSSI',True],				# Doesn't really update for whatever reason
				#['Battery Voltage',True],	# Transmits updates pretty frequently
			])
		else:
			valid_sub_name = False

		if valid_sub_name:
			BLE_Device.dp(f'{self.system_type} set BLE_Device hardware messages for {message_type} to {should_subscribe}',2)

		return valid_sub_name

	async def drain_messages(self):
		async with self.drain_lock:
			while not self.message_queue.empty():
				message = self.message_queue.get()
				for callback_uuid, callback_settings in self.callbacks.items():
					# message_type in subscriptions
					if message[0] in callback_settings[1]:
						# callback( ( dev_addr, type, key, value ) )
						await callback_settings[0]((callback_uuid,) + message)

			# Process any registrations that occurred during the above dispatch
			await self.__process_drainlock_queue()

	async def device_events(self, sender, data):
		# Bleak events get sent here
		bt_message = Decoder.decode_payload(data)
		msg_prefix = self.system_type+" "

		if bt_message['error']:
			BLE_Device.dp(msg_prefix+"ERR:"+bt_message['readable'])
			self.message_queue.put(('error','message',bt_message['readable']))

		else:
			if not await self.process_bt_message(bt_message):
				# debug for messages we've never seen before
				BLE_Device.dp(msg_prefix+"-?- "+bt_message['readable'],1)

		BLE_Device.dp("Draining for: "+bt_message['readable'],3)
		await self.drain_messages()

	# Returns false if unprocessed
	# Override in subclass, call super if you don't process the bluetooth message type
	async def process_bt_message(self, bt_message):
		msg_prefix = self.system_type+" "

		if Decoder.message_type_str[bt_message['type']] == 'port_input_format_single':
			if BLE_Device.DEBUG >= 2:
				msg = "Disabled notifications on "
				if bt_message['notifications']:
					# Returned typically after gatt write
					msg = "Enabled notifications on "

				port_text = "port "+str(bt_message['port'])
				if bt_message['port'] in self.port_data:
					# Sometimes the hub_attached_io messages don't come in before the port subscriptions do (despite the sleep() in connect())
					# So you'll get
					# peach Enabled notifications on port 3, mode 2
					# peach Attached Mario RGB Scanner on port 1 (in time)
					# peach Attached LEGO Events on port 3 (whoops, name came in late)
					# peach Enabled notifications on Mario RGB Scanner port (1), mode 0
					port_text = self.port_data[bt_message['port']]['name']+" port ("+str(bt_message['port'])+")"

				BLE_Device.dp(msg_prefix+msg+port_text+", mode "+str(bt_message['mode']), 2)

				# Getting "Enabled notifications on LEGO Events port (3), mode 2"
				# after .unregister_callback() and

		# Sent on connect, without request
		elif Decoder.message_type_str[bt_message['type']] == 'hub_attached_io':
			event = Decoder.io_event_type_str[bt_message['event']]
			if event == 'attached':
				dev = "UNKNOWN DEVICE"
				if bt_message['io_type_id'] in Decoder.io_type_id_str:
					dev = Decoder.io_type_id_str[bt_message['io_type_id']]
				else:
					dev += "_"+str(bt_message['io_type_id'])

				if bt_message['port'] in self.port_data:
					BLE_Device.dp(msg_prefix+"Re-attached "+dev+" on port "+str(bt_message['port']),2)
					self.port_data[bt_message['port']]['status'] = bt_message['event']
				else:
					BLE_Device.dp(msg_prefix+"Attached "+dev+" on port "+str(bt_message['port']),2)
					self._init_port_data(bt_message['port'], bt_message['io_type_id'])

			elif event == 'detached':
				BLE_Device.dp(msg_prefix+"Detached "+dev+" on port "+str(bt_message['port']),2)
				self.port_data[bt_message['port']]['status'] = 0x0 # io_event_type_str

			else:
				BLE_Device.dp(msg_prefix+"HubAttachedIO: "+bt_message['readable'],1)

		elif Decoder.message_type_str[bt_message['type']] == 'port_value_single':
			if not bt_message['port'] in self.port_data:
				BLE_Device.dp(msg_prefix+"WARN: Received data for unconfigured port "+str(bt_message['port'])+':'+bt_message['readable'])
			else:
				pd = self.port_data[bt_message['port']]
				if pd['name'] == 'Powered Up hub Bluetooth RSSI':
					self.decode_bt_rssi_data(bt_message['value'])
				elif pd['name'] == 'Voltage':
					self.decode_voltage_data(bt_message['value'])
				else:
					if BLE_Device.DEBUG >= 2:
						BLE_Device.dp(msg_prefix+"Data on "+self.port_data[bt_message['port']]['name']+" port"+":"+" ".join(hex(n) for n in bt_message['raw']),2)

		elif Decoder.message_type_str[bt_message['type']] == 'hub_properties':
			if not Decoder.hub_property_op_str[bt_message['operation']] == 'Update':
				# everything else is a write, so you shouldn't be getting these messages!
				BLE_Device.dp(msg_prefix+"ERR NOT UPDATE: "+bt_message['readable'])

			else:
				if not bt_message['property'] in Decoder.hub_property_str:
					BLE_Device.dp(msg_prefix+"Unknown property "+bt_message['readable'])
				else:
					if Decoder.hub_property_str[bt_message['property']] == 'Button':
						if bt_message['value']:
							BLE_Device.dp(msg_prefix+"Bluetooth button pressed!",2)
							self.message_queue.put(('event','button','pressed'))
						else:
							# Well, nobody cares if it WASN'T pressed...
							pass

					# The app seems to be able to subscribe to Battery Voltage and get it sent constantly
					elif Decoder.hub_property_str[bt_message['property']] == 'Battery Voltage':
						BLE_Device.dp(msg_prefix+"Battery is at "+str(bt_message['value'])+"%",2)
						self.message_queue.put(('info','batt',bt_message['value']))

					elif Decoder.hub_property_str[bt_message['property']] == 'Advertising Name':
						self.decode_advertising_name(bt_message)

					else:
						BLE_Device.dp(msg_prefix+bt_message['readable'],2)

		elif Decoder.message_type_str[bt_message['type']] == 'port_output_command_feedback':
			# Don't really care about these messages?  Just a bunch of queue status reporting
			BLE_Device.dp(msg_prefix+" "+bt_message['readable'],3)
			pass

		elif Decoder.message_type_str[bt_message['type']] == 'hub_alerts':
			# Ignore "status OK" messages
			if bt_message['status'] == True:
				BLE_Device.dp(msg_prefix+"ALERT! "+bt_message['alert_type_str']+" - "+bt_message['operation_str'])
				self.message_queue.put(('error','message',bt_message['alert_type_str']+" - "+bt_message['operation_str']))

		elif Decoder.message_type_str[bt_message['type']] == 'hub_actions':
			self.decode_hub_action(bt_message)

		elif Decoder.message_type_str[bt_message['type']] == 'port_info':
			await self.decode_mode_info_and_interrogate(bt_message)

		elif Decoder.message_type_str[bt_message['type']] == 'port_mode_info':
			# Debug stuff for the ports and modes, similar to list command on BuildHAT
			self.decode_port_mode_info(bt_message)

		elif Decoder.message_type_str[bt_message['type']] == 'hw_network_cmd':
			self.decode_hardware_network_command(bt_message)

		else:
			return False

		return True

	# ---- Make data useful ----
	# port_info_req response
	# 'IN': Receive data from device
	# 'OUT': Send data to device
	async def decode_mode_info_and_interrogate(self, bt_message):
		port = bt_message['port']
		if not 'num_modes' in bt_message:
			BLE_Device.dp(f'Mode combinations NOT DECODED: {bt_message["readable"]}')
			return
		else:
			BLE_Device.dp('Interrogating mode info for '+str(bt_message['num_modes'])+' modes on port '+self.port_data[port]['name']+' ('+str(port)+')')

		if 'requests_until_complete' in self.port_mode_info:
			if self.port_mode_info['requests_until_complete'] <= 0:
				BLE_Device.dp(f'WARN: Did not expect this mode info description, refusing to update: {bt_message["readable"]}')
				return

		self.port_mode_info[port]['mode_count'] = bt_message['num_modes']
		self.port_mode_info[port]['name'] = self.port_data[port]['name']
		self.port_mode_info[port]['mode_info_requests_outstanding'] = { }

		async def scan_mode(direction, port, mode):
			if not mode in self.port_mode_info[port]:
				self.port_mode_info[port][mode] = {
					'requests_outstanding':{0x0:True, 0x1:True, 0x2:True, 0x3:True, 0x4:True, 0x5:True, 0x80:True},	# Number of requests made below
					'direction':direction
				}

			# print('Request '+direction+' port '+str(port)+' info for mode '+str(mode))
			await self.write_port_mode_info_request(port,mode,0x0)	# NAME
			await self.write_port_mode_info_request(port,mode,0x1)	# RAW
			await self.write_port_mode_info_request(port,mode,0x2)	# PCT
			await self.write_port_mode_info_request(port,mode,0x3)	# SI
			await self.write_port_mode_info_request(port,mode,0x4)	# SYMBOL
			await self.write_port_mode_info_request(port,mode,0x5)	# MAPPING

			# FIXME: Throws 'Invalid use of command' if it doesn't support motor bias
			#await self.write_port_mode_info_request(port,mode,0x7)

			# Mario doesn't seem to support this?
			#await self.write_port_mode_info_request(port,mode,0x8)	# Capability bits
			await self.write_port_mode_info_request(port,mode,0x80)	# VALUE FORMAT
			await asyncio.sleep(0.3)

		bit_value = 1
		mode_number = 0
		while mode_number < 16: # or bit_value <= 32768
			if bt_message['input_bitfield'] & bit_value:
				self.port_mode_info[port]['mode_info_requests_outstanding'][mode_number] = True
				await scan_mode('IN',port,mode_number)
			bit_value <<=1
			mode_number += 1

		bit_value = 1
		mode_number = 0
		while mode_number < 16: # or bit_value <= 32768
			if bt_message['output_bitfield'] & bit_value:
				if mode_number in self.port_mode_info[port]:
					self.port_mode_info[port][mode_number]['direction'] = 'IN/OUT'
				else:
					# Can't really tell the difference between in and out request
					self.port_mode_info[port]['mode_info_requests_outstanding'][mode_number] = True
					await scan_mode('OUT',port,mode_number)

			bit_value <<=1
			mode_number += 1

		# When 'requests_outstanding' for the port and mode are done, eliminate entry in mode_info_requests_outstanding
		if not self.port_mode_info[port]['mode_info_requests_outstanding']:
			self.port_mode_info[port].pop('mode_info_requests_outstanding',None)

		self.port_mode_info['requests_until_complete'] -= 1
		if self.port_mode_info['requests_until_complete']  == 0:
			self.port_mode_info.pop('requests_until_complete',None)
			BLE_Device.dp(json.dumps(self.port_mode_info, indent=4))
			BLE_Device.dp("Port interrogation complete!")

	def decode_port_mode_info(self, bt_message):

		if 'requests_until_complete' in self.port_mode_info:
			if self.port_mode_info['requests_until_complete'] <= 0:
				BLE_Device.dp(f'WARN: Did not expect this mode info report, refusing to update: {bt_message["readable"]}')
				return

		readable =''
		port = bt_message['port']
		mode = bt_message['mode']

		if port in self.port_data:
			pdata = self.port_data[port]
			readable += pdata['name']+' ('+str(port)+')'
		else:
			readable += 'Port ('+str(port)+')'

		readable += ' mode '+str(mode)

		# FIXME: Stuff all this in a structure and then dump it out
		if not mode in self.port_mode_info[port]:
			print(f'ERROR: MODE {mode} MISSING FOR PORT {port}: SHOULD HAVE BEEN SET in decode_mode_info_and_interrogate. Dumping: {bt_message["readable"]}')
			print("Keys:")
			print(self.port_mode_info[port].keys())
			return

		if bt_message['mode_info_type'] in Decoder.mode_info_type_str:
			readable += ' '+Decoder.mode_info_type_str[bt_message['mode_info_type']]+':'
		else:
			readable += ' infotype_'+str(bt_message['mode_info_type'])+':'

		# Name
		decoded = True
		if bt_message['mode_info_type'] == 0x0:
			# readable += bt_message['name']
			self.port_mode_info[port][mode]['name'] = bt_message['name']
		# Raw
		elif bt_message['mode_info_type'] == 0x1:
			#readable += ' Min: '+str(bt_message['raw']['min'])+' Max: '+str(bt_message['raw']['max'])
			self.port_mode_info[port][mode]['raw'] = {
				'min':bt_message['raw']['min'],
				'max':bt_message['raw']['max']
			}
		# Percentage range window scale
		elif bt_message['mode_info_type'] == 0x2:
			#readable += ' Min: '+str(bt_message['pct']['min'])+' Max: '+str(bt_message['pct']['max'])
			self.port_mode_info[port][mode]['pct'] = {
				'min':bt_message['pct']['min'],
				'max':bt_message['pct']['max']
			}
		# SI Range
		elif bt_message['mode_info_type'] == 0x3:
			#readable += ' Min: '+str(bt_message['si']['min'])+' Max: '+str(bt_message['si']['max'])
			self.port_mode_info[port][mode]['si'] = {
				'min':bt_message['si']['min'],
				'max':bt_message['si']['max']
			}
		# Symbol
		elif bt_message['mode_info_type'] == 0x4:
			#readable += bt_message['symbol']
			self.port_mode_info[port][mode]['symbol'] = bt_message['symbol']
		elif bt_message['mode_info_type'] == 0x5:
			# Mapping
			# FIXME
			#readable += bt_message['readable']
			self.port_mode_info[port][mode]['mapping_readable'] = bt_message['readable']
		elif bt_message['mode_info_type'] == 0x7:
			#readable += ' Motor bias: '+bt_message['motor_bias']
			self.port_mode_info[port][mode]['motor_bias'] = bt_message['motor_bias']
		elif bt_message['mode_info_type'] == 0x8:
			# Capability bits
			# FIXME
			#readable += bt_message['readable']
			self.port_mode_info[port][mode]['capability_readable'] = bt_message['readable']


		# Value format
		elif bt_message['mode_info_type'] == 0x80:
			readable = ''
			readable += ' '+str(bt_message['datasets']) + ' '+ bt_message['dataset_type']+ ' datasets'
			readable += ' with '+str(bt_message['total_figures'])+' total figures and '+str(bt_message['decimals'])+' decimals'

			self.port_mode_info[port][mode]['value_readable'] = readable

		else:
			decoded = False
			BLE_Device.dp('No decoder for this:')

		if not decoded:
			BLE_Device.dp('Not decoded:'+readable)
		else:
			#BLE_Device.dp(readable)
			pass


		if 'requests_outstanding' in self.port_mode_info[port][mode]:
			if bt_message['mode_info_type'] in self.port_mode_info[port][mode]['requests_outstanding']:
				self.port_mode_info[port][mode]['requests_outstanding'].pop(bt_message['mode_info_type'],None)
			else:
				print("DUPLICATE mode info type "+hex(bt_message['mode_info_type'])+' on port '+str(port)+' mode '+str(mode))

			# Remove requests_outstanding if zero outstanding (and all the modes with it)
			if not self.port_mode_info[port][mode]['requests_outstanding']:
				self.port_mode_info[port][mode].pop('requests_outstanding',None)
				if mode in self.port_mode_info[port]['mode_info_requests_outstanding']:
					self.port_mode_info[port]['mode_info_requests_outstanding'].pop(mode,None)

		else:
			print(f"EXTRA mode info type {hex(bt_message['mode_info_type'])} on port {port} mode {mode} DUMP:{bt_message['readable']}")

	def decode_bt_rssi_data(self, data):
		# Lower numbers are larger distances from the computer
		rssi8 = int.from_bytes(data, byteorder="little", signed=True)
		BLE_Device.dp("RSSI: "+str(rssi8))

	def decode_voltage_data(self,data):
		# FIXME: L or S and what do they mean?
		volts16 = int.from_bytes(data, byteorder="little", signed=False)
		BLE_Device.dp("Voltage: "+str(volts16)+ " millivolts")

	def decode_hub_action(self, bt_message):
		BLE_Device.dp(self.system_type+" "+bt_message['action_str'],2)
		# Decoder.hub_action_type
		if bt_message['action'] == 0x30:
			self.message_queue.put(('event','power','turned_off'))
		elif bt_message['action'] == 0x31:
			self.message_queue.put(('event','bt','disconnected'))
		else:
			BLE_Device.dp(self.system_type+" unknown hub action "+hex(bt_message['action']),1)

	def decode_hardware_network_command(self, bt_message):
		if 'command' in bt_message:
			if bt_message['command'] == 'connection_request':
				message = None
				if bt_message['value'] == 'button_up':
					message = ('connection_request','button','up')
				elif bt_message['value'] == 'button_down':
					message = ('connection_request','button','down')
				self.message_queue.put(message)
			else:
				BLE_Device.dp(self.system_type+" unknown hw command: "+bt_message['readable'],1)
		else:
			BLE_Device.dp(self.system_type+" "+bt_message['readable'],1)

	def decode_advertising_name(self, bt_message):
		# FIXME: Clearly this should be a message and not a debugging statement
		msg_prefix = self.system_type+" "
		BLE_Device.dp(msg_prefix+"Advertising as \""+str(bt_message['value'])+"\"",2)

	# ---- Random stuff ----

	def dp(pstr, level=1):
		if BLE_Device.DEBUG:
			if BLE_Device.DEBUG >= level:
				print(pstr)

	# ---- Bluetooth port writes ----
	async def interrogate_ports(self):
		BLE_Device.dp("Starting port interrogation...")
		self.port_mode_info['requests_until_complete'] = 0
		for port, data in self.port_data.items():
			# This should be done as some kind of batch, blocking operation
			self.port_mode_info['requests_until_complete'] += 1

			await self.write_port_info_request(port, True)
			await asyncio.sleep(0.2)

	async def set_port_subscriptions(self, portlist):
		# array of 4-item arrays [port, mode, delta interval, subscribe on/off]
		if isinstance(portlist, Iterable):
			for port_settings in portlist:
				if isinstance(port_settings, Iterable) and len(port_settings) == 4:

					# Port Input Format Setup (Single) message
					# Sending this results in port_input_format_single response

					payload = bytearray([
						0x0A,				# length
						0x00,
						0x41,				# Port input format (single)
						port_settings[0],	# port
						port_settings[1],	# mode
					])

					# delta interval (uint32)
					# 5 is what was suggested by https://github.com/salendron/pyLegoMario
					# 88010 Controller buttons for +/- DO NOT WORK without a delta of zero.
					# Amusingly, this is strongly _not_ recommended by the LEGO docs
					# Kind of makes sense, though, since they are discrete (and debounced, I assume)
					payload += port_settings[2].to_bytes(4,byteorder='little',signed=False)

					if port_settings[3]:
						payload.append(0x1)		# notification enable
					else:
						payload.append(0x0)		# notification disable
					#print(" ".join(hex(n) for n in payload))
					await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
					await asyncio.sleep(1)

	async def set_updates_for_hub_properties(self, hub_properties):
		# array of [str(hub_property_str),bool] arrays
		if isinstance(hub_properties, Iterable):
			for hub_property_settings in hub_properties:
				if isinstance(hub_property_settings, Iterable) and len(hub_property_settings) == 2:
					hub_property = str(hub_property_settings[0])
					hub_property_set_updates = bool(hub_property_settings[1])
					if hub_property in Decoder.hub_property_ints:
						hub_property_int = Decoder.hub_property_ints[hub_property]
						if hub_property_int in Decoder.hub_properties_that_update:
							hub_property_operation = 0x3
							if hub_property_set_updates:
								BLE_Device.dp(f'{self.system_type} Requesting updates for hub property: {hub_property}',2)
								hub_property_operation = 0x2
							else:
								BLE_Device.dp(f'{self.system_type} Disabling updates for hub property: {hub_property}',2)
								pass
							hub_property_update_subscription_bytes = bytearray([
								0x05,	# len
								0x00,	# padding but maybe stuff in the future (:
								0x1,	# 'hub_properties'
								hub_property_int,
								hub_property_operation
							])
							await self.client.write_gatt_char(BLE_Device.characteristic_uuid, hub_property_update_subscription_bytes)
							await asyncio.sleep(0.1)
						else:
							BLE_Device.dp("Decoder chars says not able to subscribe to: "+hub_property,2)

	async def turn_off(self):
		name_update_bytes = bytearray([
			0x04,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x2,	# 'hub_actions'
			0x1		# Decoder.hub_action_type: 'Switch Off Hub'  (Don't use 0x2f, powers down as if you yanked the battery)
		])
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)

	async def request_name_update(self):
		# Triggers hub_properties message
		name_update_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x1,	# 'Advertising Name'
			0x5		# 'Request Update'
		])
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)

	async def request_version_update(self):
		# Triggers hub_properties message
		name_update_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x3,	# 'Firmware version'
			0x5		# 'Request Update'
		])
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)

		name_update_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x4,	# 'Hardware version'
			0x5		# 'Request Update'
		])
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)

	async def request_battery_update(self):
		# Triggers hub_properties message
		name_update_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x6,	# 'Battery Percentage'
			0x5		# 'Request Update'
		])
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)

	async def write_mode_data_RGB_color(self, port, color):
		if color not in Decoder.rgb_light_colors:
			return

		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x81,	# Command: port_output_command
			# end header
			port,
			0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
			0x51,	# Subcommand: WriteDirectModeData
			0x0,	# Mode (Could be 1 according to LEGO BTLE docs?)
			color
		])
		payload[0] = len(payload)
		# BLE_Device.dp(self.system_type+" Debug RGB Write"+" ".join(hex(n) for n in payload))
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
		await asyncio.sleep(0.1)

	async def write_port_mode_info_request(self, port, mode, infotype):
		if mode < 0 or mode > 255:
			BLE_Device.dp('ERROR: Invalid mode '+str(mode)+' for mode info request')
			return
		if not infotype in Decoder.mode_info_type_str:
			BLE_Device.dp('ERROR: Invalid information type '+hex(infotype)+' for mode info request')
			return

		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x22,	# Command: port_mode_info_req
			# end header
			port,
			mode,
			infotype	# 0-8 & 0x80
		])
		payload[0] = len(payload)

# FIXME: Check for range issues with bluetooth  on write_gatt_char (device goes too far away)
#    raise BleakError("Characteristic {} was not found!".format(char_specifier))
#bleak.exc.BleakError: Characteristic 00001624-1212-efde-1623-785feabcd123 was not found!

# or it just disappears
# AttributeError: 'NoneType' object has no attribute 'write_gatt_char'
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
		await asyncio.sleep(0.2)

	async def write_port_info_request(self, port, mode_info=False):
		# 0: Request port_value_single value
		# 1: Request port_info for port modes
		mode_int = 0x0
		if mode_info:
			mode_int = 1
		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x21,	# Command: port_info_req
			# end header
			port,
			mode_int
		])
		payload[0] = len(payload)
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
		await asyncio.sleep(0.2)
