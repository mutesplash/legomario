import asyncio
import uuid
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .Decoder import Decoder, HProp

from .LPF_Devices import *
from .LPF_Devices.LPF_Device import generate_valid_lpf_message_types

from .HubProperty import HubProperty

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
		'device_ready',
		'connection_request',
		'property',
	)

	lpf_message_types = generate_valid_lpf_message_types()

	device_property_exclusion_str = (
		'Mario Volume',
	)

	characteristic_uuid = '00001624-1212-efde-1623-785feabcd123'
	hub_service_uuid = '00001623-1212-efde-1623-785feabcd123'

	# ok, but what is service ID F000FFC0-0451-4000-B000-000000000000 with the
	# following characteristic IDs for LEGO Mario?
	# FOTA?  OAD Service? Texas Instruments OTA firmware download?
	# https://software-dl.ti.com/lprf/simplelink_cc2640r2_latest/docs/blestack/ble_user_guide/html/oad-ble-stack-3.x/oad_profile.html
	# F000FFC1-0451-4000-B000-000000000000
	# F000FFC2-0451-4000-B000-000000000000
	# F000FFC5-0451-4000-B000-000000000000

	# ---- Initializations, obviously ----

	def __init__(self, advertisement_data=None):

		self.system_type = None
		self.client = None
		self.connected = False

		self.gatt_send_rate_limit = 0.1
		self.mode_probe_rate_limit = 0.3

		# Override in subclass __init__ and set to a list of hex values for
		# Mode Information Types over which the device throws errors when doing
		# port mode information requests ( interrogate_ports() )
		self.mode_probe_ignored_info_types = ()

		# keep around for... whatever?
		self.device = None
		self.advertisement = None
		self.address = None

		self.disconnect_callback = lambda bleak_dev: BLE_Device._bleak_disconnect(self, bleak_dev)
		# This is such a fun trick, we'll do it twice.
		# Give connected devices this function to let them send their own gatt messages
		self.gatt_writer = lambda payload: BLE_Device._gatt_send(self, payload)

		self.port_mode_info = {
			'port_count':0,
			'requests_until_complete':0		# Port interrogation
		}

		self.message_queue = SimpleQueue()				# Messages to send to callbacks
		self.drainlock_changes_queue = SimpleQueue()	# Changes to those callbacks

		# Message type subscriptions reference count
		self.BLE_event_subscriptions = {}
		self._reset_event_subscription_counters()

		self.callbacks = {}
		# UUID indexed tuples of...
		# 0: callback function
		# 1: Tuple of message type subscriptions

		self.lock = asyncio.Lock()			# Connect lock
		self.drain_lock = asyncio.Lock()	# Draining message_queue

		self.ports = {}
		self.properties = {}

		self._init_hub_properties()

	def _init_hub_properties(self):
		for property_int in Decoder.hub_property_str:
			if Decoder.hub_property_str[property_int] not in self.device_property_exclusion_str:
				self.properties[property_int] = HubProperty(property_int)

	async def _init_port_data(self, bt_message):
		port = bt_message['port']
		port_id = bt_message['io_type_id']
		port_classname = LPF_class_for_type_id(port_id)
		self.port_mode_info['port_count'] += 1
		if port_classname:
			# https://stackoverflow.com/a/547867
			port_module = __import__('BTLego.LPF_Devices.'+port_classname, fromlist=[port_classname])
			port_classobj = getattr(port_module, port_classname)
			self.ports[port] = port_classobj()
			self.ports[port].port = port
			self.ports[port].port_id = port_id
			self.ports[port].hw_ver_str = bt_message['hw_ver_str']
			self.ports[port].fw_ver_str = bt_message['sw_ver_str']
			self.ports[port].name = Decoder.io_type_id_str[port_id]
			self.ports[port].status = 0x1		# Decoder.io_event_type_str[0x1]
			for message_type, sub_count in self.BLE_event_subscriptions.items():
				if sub_count > 0:
					await self.ports[port].subscribe_to_messages(message_type, True, self.gatt_writer)
					# On init, don't have to unsub

			self.message_queue.put(('device_ready', port_id, port))
			return True
		else:
			BLE_Device.dp(f'Class {self.__class__.__name__} contains unknown device type id {port_id} on port {port}',2)
			return False

	def _detach_lpf_device(self,port):
		if port in self.ports:
			lpf_dev = self.ports[port]
			lpf_dev.status = 0x0		# Decoder.io_event_type_str[0x0]
			del self.ports[port]

	def _reset_port_mode_info(self):
		self.port_mode_info['requests_until_complete'] = 0

		for port in list(self.port_mode_info):
			if isinstance(port,int) or port.isdigit():
				if 'mode_info_requests_outstanding' in self.port_mode_info[port]:
					self.port_mode_info[port].pop('mode_info_requests_outstanding',None)

				for mode in list(self.port_mode_info[port]):
					if isinstance(mode,int) or mode.isdigit():
						self.port_mode_info[port].pop(mode,None)

	# Overrideable
	async def _inital_connect_updates(self):
		await self.send_property_message( HProp.AD_NAME, ('get', None) )

		# Init trigger (BUT NOT ALL PORTS INIT)
		await self.send_property_message( HProp.FIRMWARE, ('get', None) )

	# Override in subclass and call super if you subclass to initialize BLE_event_subscriptions with all available message types
	def _reset_event_subscription_counters(self):
		for message_type in BLE_Device.message_types:
			self.BLE_event_subscriptions[message_type] = 0;
		for message_type in self.message_types:
			self.BLE_event_subscriptions[message_type] = 0;
		for message_type in self.lpf_message_types:
			self.BLE_event_subscriptions[message_type] = 0;

	# ---- Things Normal People Can Do ----
	# (Not really all of them, there are some direct bluetooth things below)

	async def dump_status(self):
		BLE_Device.dp("EVENT SUBS\n"+json.dumps(self.BLE_event_subscriptions, indent=4))
		BLE_Device.dp("PORT LIST\n")
		for port in self.ports:
			dev = self.ports[port]
			BLE_Device.dp(f'\tPort {dev.port} {dev.name} : {dev.devtype} {dev.mode_subs} HW:{dev.hw_ver_str} FW:{dev.fw_ver_str}')
		BLE_Device.dp("PROPERTY LIST\n")
		for prop_int, propobj in self.properties.items():
			BLE_Device.dp(f'\tProperty {propobj.name} ({propobj.reference_number}) Subscribed: {propobj.subscribed}')
		BLE_Device.dp("CALLBACKS\n"+json.dumps(self.callbacks, indent=4, default=lambda function: '<function callback>'))
		BLE_Device.dp("PORT MODE INFO\n"+json.dumps(self.port_mode_info, indent=4))

	async def connect(self, device, advertisement_data):
		async with self.lock:
			self.system_type = Decoder.determine_device_shortname(advertisement_data)
			BLE_Device.dp("Connecting to "+str(self.system_type)+"...",2)
			self.device = device
			self.advertisement = advertisement_data
			try:
				self.client = BleakClient(device.address, self.disconnect_callback)
				await self.client.connect()
				if not self.client.is_connected:
					BLE_Device.dp("Failed to connect after client creation")
					return
				BLE_Device.dp("Connected to "+self.system_type+"! ("+str(device.name)+")",2)
				self.connected = True
				self.address = device.address
				await self.client.start_notify(BLE_Device.characteristic_uuid, self._device_events)

				# turn back on everything everybody registered for (For reconnection)
				for event_sub_type,sub_count in self.BLE_event_subscriptions.items():
					if sub_count > 0:
						if not await self._set_hardware_subscription(event_sub_type, True):
							BLE_Device.dp("INVALID Subscription option on connect:"+event_sub_type)

				await self._inital_connect_updates()

			except Exception as e:
				BLE_Device.dp("Unable to connect to "+str(device.address) + ": "+str(e))
		self.message_queue.put(('info','player',self.system_type))

	async def disconnect(self):
		async with self.lock:
			self.connected = False
			BLE_Device.dp(self.system_type+" has disconnected.",2)

	def _bleak_disconnect(self, bleak_dev):
		"""Called by the BleakClient when disconnected"""
		print(f'Bleak disconnect {self.system_type}: {bleak_dev.address}')
		# This whole function is a bit annoying as it isn't awaited by Bleak
		# and therefore can't be called async, so it can't lock to set this
		# variable.
		# The disconnect callback for BleakClient also can't be on an instance
		# of a class, because that needs to be passed self, and the callback
		# takes only one parameter: BleakClient
		# Therefore in init, there's a lambda that closes over self to pass it
		# here and calls this function on the class, allowing BleakClient to take
		# that lambda as the callback, which means it's a bit deceptive to use
		# self as the variable name, but everything is dying here so... WHATEVER
		self.connected = False
		# Note about why self has to be passed, anyway
		# https://stackoverflow.com/a/10003918

		# Adding anything to the message_queue won't get kicked until the device is reconnected
		thisloop = asyncio.get_running_loop()
		if thisloop:
			if thisloop.is_running():
				pass
				# Putting anything on thisloop doesn't work.  The event doesn't get drained until the device is reconnected because it's driven by Bleak's callback

	async def is_connected(self):
		async with self.lock:
			return self.connected

	# set/unset registrations separately
	async def register_callback(self, callback):
		callback_uuid = str(uuid.uuid4())
		self.drainlock_changes_queue.put(('callback', 'register', (callback_uuid,callback)))

		# If outside of the drain, process now!
		if not self.drain_lock.locked():
			async with self.drain_lock:
				await self.__process_drainlock_queue()

		return callback_uuid

	async def unregister_callback(self, callback_uuid):
		self.drainlock_changes_queue.put(('callback', 'unregister', (callback_uuid,)))

		# If outside of the drain, process now!
		if not self.drain_lock.locked():
			async with self.drain_lock:
				await self.__process_drainlock_queue()

	# Hmm... just because this returns true doesn't mean you're going to get the messages (see failure modes in __process_drainlock_queue)
	async def subscribe_to_messages_on_callback(self, callback_uuid, message_type, subscribe=True):
		# Not going to check if the callback is valid here, because it could be on the queue

		# Contains all message_types for the class after _reset_event_subscription_counters() in subclasses
		# FIXME: Not strictly true.  This is ALL of the subscriptions that are possible.
		if not message_type in self.BLE_event_subscriptions:
			BLE_Device.dp(f'Class {self.__class__.__name__} can\'t subscribe to {message_type}',2)
			return False

		self.drainlock_changes_queue.put(('subscription', 'change', (callback_uuid,message_type,subscribe)))

		# If outside of the drain, process now!
		if not self.drain_lock.locked():
			async with self.drain_lock:
				await self.__process_drainlock_queue()

		return True

	# ---- Message processing ----

	# MUST be called within drain_lock because commands in here modify callbacks
	# and their subscriptions and therefore the drain loop processing.
	# Callback register, unregister, and message subscribe have to be processed
	# AFTER the message queue is drained, but WITHIN the (drain)lock on the queue
	# since dispatching anything in the queue will be affected
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

					BLE_Device.dp(f'Unusbscribe processing {callback_uuid}',3)
					for subscription in current_subscriptions:
						self._set_callback_subscriptions(parameters[0], subscription, False)

						if (self.BLE_event_subscriptions[subscription] <= 0):
							if not await self._set_hardware_subscription(subscription, False):
								BLE_Device.dp(f'UUID {callback_uuid} requested unsubscribe... but.. the device was not connected?')
					BLE_Device.dp(f'Finished processing unsubscribes {callback_uuid}',3)

					self.callbacks.pop(callback_uuid, None)

				# FIXME: Doesn't actually take the third parameter
				# (callback_uuid,callback,subscription_tuple)
				elif change_order[1] == 'register':
					BLE_Device.dp(f'Registering callback {parameters[0]}',2)
					self.callbacks[parameters[0]] = (parameters[1], ())

			# Caller verifies message_type
			# (callback_uuid, message_type, boolean_subscription)
			elif change_order[0] == 'subscription' and change_order[1] == 'change':
				BLE_Device.dp(f'Requesting {parameters[2]} subscription to {parameters[1]} on callback {parameters[0]}',2)

				# first subscribing callback: turn on the event	OR last subscribing callback: turn off the subscription
				# Otherwise, don't bother the hardware
				if (self.BLE_event_subscriptions[parameters[1]] <= 0 and parameters[2]) or (self.BLE_event_subscriptions[parameters[1]] == 1 and not parameters[2]):
					self._set_callback_subscriptions(parameters[0], parameters[1], parameters[2])
					if not await self._set_hardware_subscription(parameters[1], parameters[2]):
						BLE_Device.dp("INVALID Subscription option:"+parameters[1])
				else:
					pass
					#BLE_Device.dp(f'\tNOT BOTHERING: Setting to {parameters[2]} would not change to/from zero the sub count for this message type ({parameters[1]}) from '+str(self.BLE_event_subscriptions[parameters[1]]),2)

	async def _drain_messages(self):
		async with self.drain_lock:
			while not self.message_queue.empty():
				message = self.message_queue.get()
				served = False
				for callback_uuid, callback_settings in self.callbacks.items():
					# message_type in subscriptions
					if message[0] in callback_settings[1]:
						# callback( ( dev_addr, type, key, value ) )
						await callback_settings[0]((callback_uuid,) + message)
						served = True
				if not served:
					BLE_Device.dp(f'{self.system_type} had no subscribers for message:{message}')

			# Process any registrations that occurred during the above dispatch
			await self.__process_drainlock_queue()

	# return the tuple of subscriptions that were set
	# Assumes you filtered this to only valid message types
	def _set_callback_subscriptions(self, callback_uuid, message_type, subscribe=True):
		if not callback_uuid in self.callbacks:
			# Could happen with getting deferred in the queue?
			BLE_Device.dp(f'Given UUID {callback_uuid} disappeared.  Failed to subscribe to {message_type}')
			return False

		do_nothing = False
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
			BLE_Device.dp(f'Callback subscriptions unchanged after requesting {message_type} to {subscribe}',3)
		else:
			if subscribe:
				self.BLE_event_subscriptions[message_type] += 1
				BLE_Device.dp(f'Setting callback {callback_uuid} subscription to {message_type}',3)
			else:
				self.BLE_event_subscriptions[message_type] -= 1
				BLE_Device.dp(f'Removing callback {callback_uuid} subscription to {message_type}',3)

			self.callbacks[callback_uuid] = (callback_settings[0], new_subscriptions)

		return new_subscriptions

	# Checks all Properties and Ports for LPF devices that handle the given message_type
	# Subscribes or unsubscribes to these messages as requested
	async def _set_hardware_subscription(self, message_type, should_subscribe=True):

		if not message_type in self.BLE_event_subscriptions:
			print(f'No known devices generate {message_type}')
			return False

		for port in self.ports:
			await self.ports[port].subscribe_to_messages(message_type, should_subscribe, self.gatt_writer)
		return True

	async def _set_property_subscription(self, property_int, should_subscribe=True):
		if property_int in self.properties:
			payload = self.properties[property_int].gatt_payload_for_subscribe(should_subscribe)
			if payload:
				await self._gatt_send(payload)
		else:
			BLE_Device.dp(f'{self.system_type} does not have a property numbered {property_int}',2)

	# Bleak events get sent here
	async def _device_events(self, sender, data):
		bt_message = Decoder.decode_payload(data)
		msg_prefix = self.system_type+" "
		if bt_message['error']:
			BLE_Device.dp(msg_prefix+"ERR:"+bt_message['readable'])
			self.message_queue.put(('error','message',bt_message['readable']))

		else:
			if not await self._process_bt_message(bt_message):
				# debug for messages we've never seen before
				BLE_Device.dp(msg_prefix+"-?- "+bt_message['readable'],1)

		BLE_Device.dp(f'{self.system_type} Draining for: '+bt_message['readable'],3)
		await self._drain_messages()

	# Returns false if unprocessed
	# Override in subclass, call super if you don't process the bluetooth message type
	async def _process_bt_message(self, bt_message):
		msg_prefix = self.system_type+" "

		if Decoder.message_type_str[bt_message['type']] == 'port_input_format_single':
			if BLE_Device.DEBUG >= 2:
				msg = "Disabled notifications on "
				if bt_message['notifications']:
					# Returned typically after gatt write
					msg = "Enabled notifications on "

				port_text = "port "+str(bt_message['port'])

				if bt_message['port'] in self.ports:
					port_text = self.ports[bt_message['port']].name+" port ("+str(bt_message['port'])+")"

				BLE_Device.dp(msg_prefix+msg+port_text+", mode "+str(bt_message['mode']), 2)

		# Sent on connect, without request
		elif Decoder.message_type_str[bt_message['type']] == 'hub_attached_io':
			event = Decoder.io_event_type_str[bt_message['event']]

			reattached = -1
			if bt_message['port'] in self.ports:
				reattached = bt_message['port']

			if event == 'attached':
				dev = "UNKNOWN DEVICE"
				if bt_message['io_type_id'] in Decoder.io_type_id_str:
					dev = Decoder.io_type_id_str[bt_message['io_type_id']]
				else:
					dev += "_"+str(bt_message['io_type_id'])

				if reattached != -1:
					BLE_Device.dp(msg_prefix+"Re-attached "+dev+" on port "+str(bt_message['port']),2)
					self.ports[reattached].status = bt_message['event']
				else:
					BLE_Device.dp(msg_prefix+"Attached "+dev+" on port "+str(bt_message['port']),2)
					# Can't mess with the port list outside of the drain lock
					async with self.drain_lock:
						if not await self._init_port_data(bt_message):
							if bt_message['io_type_id'] in Decoder.io_type_id_str:
								BLE_Device.dp(msg_prefix+" NO CLASS EXISTS FOR LPF ATTACHED DEVICE "+Decoder.io_type_id_str[bt_message['io_type_id']]+": "+str(bt_message['readable']))
							else:
								BLE_Device.dp(msg_prefix+" TOTALLY UNKNOWN DEVICE "+str(bt_message['io_type_id'])+": "+str(bt_message['readable']))

			elif event == 'detached':
				BLE_Device.dp(msg_prefix+"Detached device on port "+str(bt_message['port']),2)
				self._detach_lpf_device(bt_message['port'])

			else:
				BLE_Device.dp(msg_prefix+"HubAttachedIO: "+bt_message['readable'],1)

		elif Decoder.message_type_str[bt_message['type']] == 'port_value_single':

			device = None
			if bt_message['port'] in self.ports:
				device = self.ports[bt_message['port']]
				if device:
					if bt_message['port'] != device.port:
						print("CONSISTENCY ERROR: DEVICE ON PORT "+str(bt_message['port'])+f" NOT EQUAL TO PORT {device.port} IN CLASS ")
						# FIXME: Harsh?
						quit()

			if not device:
				BLE_Device.dp(f"{msg_prefix} WARN: Received data for unconfigured port "+str(bt_message['port'])+':'+bt_message['readable'])
			else:
				message = device.decode_pvs(bt_message['port'], bt_message['value'])
				if message:
					if len(message) == 3:
						self.message_queue.put(message)
					elif len(message) == 2:
						# FIXME
						# Ha ha, pushing out the need to use the logging feature to sometime in the future
						BLE_Device.dp(f'{msg_prefix}{message[0]} on {device.name} port while processing PVS:{message[1]}',1)
					else:
						# SHOULD be a No-op aka ( None, )
						BLE_Device.dp(f'{msg_prefix} {device.name} declared NO-OP for PVS:'+bt_message['readable'],2)
						pass
				else:
					BLE_Device.dp(f"{msg_prefix} {device.name} FAILED TO DECODE PVS DATA:"+" ".join(hex(n) for n in bt_message['value']))

		elif Decoder.message_type_str[bt_message['type']] == 'hub_properties':
			if not Decoder.hub_property_op_str[bt_message['operation']] == 'Update':
				# everything else is a write, so you shouldn't be getting these messages!
				BLE_Device.dp(msg_prefix+"ERROR: THIS CLIENT DOES NOT UPDATE: "+bt_message['readable'])

			else:
				if not bt_message['property'] in Decoder.hub_property_str:
					BLE_Device.dp(msg_prefix+"Unknown property "+bt_message['readable'])
				else:
					prop_id = bt_message['property']
					self._decode_property(prop_id, bt_message['value'])
					self.message_queue.put( ('property', prop_id, bt_message['value']) )

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
			self._decode_hub_action(bt_message)

		elif Decoder.message_type_str[bt_message['type']] == 'port_info':
			await self._decode_mode_info_and_interrogate(bt_message)

		elif Decoder.message_type_str[bt_message['type']] == 'port_mode_info':
			# Debug stuff for the ports and modes, similar to list command on BuildHAT
			self._decode_port_mode_info(bt_message)

		elif Decoder.message_type_str[bt_message['type']] == 'hw_network_cmd':
			self._decode_hardware_network_command(bt_message)

		else:
			return False

		return True

	# Override if you wanna decode a property to send _additional_ messages
	def _decode_property(self, prop_id, value):
		pass

	# ---- Make data useful for the processing ----
	# port_info_req response
	# 'IN': Receive data from device
	# 'OUT': Send data to device
	async def _decode_mode_info_and_interrogate(self, bt_message):
		port = bt_message['port']
		device = self.ports[port]
		if not 'num_modes' in bt_message:
			if 'mode_combinations' in bt_message:
				self.port_mode_info[port]['combinations'] = bt_message['mode_combinations']
			else:
				print(f'ERROR: Mode combinations NOT DECODED: {bt_message["readable"]}')
			return
		else:
			BLE_Device.dp('Interrogating mode info for '+str(bt_message['num_modes'])+' modes on port '+device.name+' ('+str(port)+')')

		if 'requests_until_complete' in self.port_mode_info:
			if self.port_mode_info['requests_until_complete'] <= 0:
				BLE_Device.dp(f'WARN: Did not expect this mode info description, refusing to update: {bt_message["readable"]}')
				return

		if not port in self.port_mode_info:
			self.port_mode_info[port] = {}

		self.port_mode_info[port]['mode_count'] = bt_message['num_modes']
		self.port_mode_info[port]['name'] = device.name
		self.port_mode_info[port]['mode_info_requests_outstanding'] = { }

		# Does not note the entire bt_message['port_mode_capabilities']
		# Mostly because i/o is redundant
		# IE: {'output': True, 'input': True, 'logic_combineable': True, 'logic_synchronizeable': False}

		if bt_message['port_mode_capabilities']['logic_synchronizeable']:
			self.port_mode_info[port]['virtual_port_capable'] = True

		if bt_message['port_mode_capabilities']['logic_combineable']:
			# This is a signal to check for combinations (3.15.2)
			await asyncio.sleep(self.mode_probe_rate_limit)
			await self._write_port_info_request(port, 0x2)

		async def scan_mode(direction, port, mode):
			if not mode in self.port_mode_info[port]:
				self.port_mode_info[port][mode] = {
					'requests_outstanding':{
						0x0:True,	# NAME
						0x1:True,	# RAW
						0x2:True,	# PCT
						0x3:True,	# SI
						0x4:True,	# SYMBOL
						0x5:True,	# MAPPING
						0x7:True,	# Mario throws 'Invalid use of command' if it doesn't support motor bias, any other BLE Lego things support it?
						0x8:True,	# Mario doesn't seem to support Capability bits
						0x80:True	# VALUE FORMAT
					},
					'direction':direction
				}

				for mode_info_type_number in self.mode_probe_ignored_info_types:
					del self.port_mode_info[port][mode]['requests_outstanding'][mode_info_type_number]

			frozen_requests = list(self.port_mode_info[port][mode]['requests_outstanding'].items())
			for hexkey, requested in frozen_requests:
				if requested:
#					BLE_Device.dp(f'\tRequest {direction} port {port} info for mode {mode} key {hexkey}')

					await asyncio.sleep(self.mode_probe_rate_limit)
					await self._write_port_mode_info_request(port,mode,hexkey)

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
					# Already scanned during the IN loop
					self.port_mode_info[port][mode_number]['direction'] = 'IN/OUT'
				else:
					# Can't really tell the difference between in and out request
					self.port_mode_info[port]['mode_info_requests_outstanding'][mode_number] = True
					await scan_mode('OUT',port,mode_number)
			else:
				if mode_number + 1 <= self.port_mode_info[port]['mode_count']:
					if not mode_number in self.port_mode_info[port]:
						# Neither IN nor OUT.  As seen on the Vision sensor, mode 8
						await scan_mode('NO-IO',port,mode_number)

			bit_value <<=1
			mode_number += 1

		# When 'requests_outstanding' for the port and mode are done, eliminate entry in mode_info_requests_outstanding
		# FIXME: Sometimes this doesn't trigger and leaves trash??
		# IE:
		#	"mode_info_requests_outstanding": {},
		if not self.port_mode_info[port]['mode_info_requests_outstanding']:
			self.port_mode_info[port].pop('mode_info_requests_outstanding',None)

		self.port_mode_info['requests_until_complete'] -= 1
		if self.port_mode_info['requests_until_complete']  == 0:

			# FIXME: If there's an error getting all this information, requests_outstanding and mode_info_requests_outstanding
			# will be littered across the dictionary.  How about finding it, trashing it,
			# and starting over?

			bt_corruption = False

			for port in self.port_mode_info:
				if isinstance(port,int) or port.isdigit():
					# Redundant error
					#if 'mode_info_requests_outstanding' in self.port_mode_info[port]:
					#	self.message_queue.put(('error','message',f'Mode info requests were still outstanding for port {port}'))
					#	bt_corruption = True

					for mode in self.port_mode_info[port]:
						if isinstance(mode,int) or mode.isdigit():
							if 'requests_outstanding' in self.port_mode_info[port][mode]:
								self.message_queue.put(('error','message',f'Mode info requests were still outstanding for port {port} mode {mode}'))
								bt_corruption = True

			self.port_mode_info.pop('requests_until_complete',None)
			if bt_corruption:
				# Blank on error
				self.message_queue.put(('info','port_json','')) # , indent=4
				BLE_Device.dp(f'DUMPING INCOMPLETE PORT JSON: {json.dumps(self.port_mode_info)}')
			else:
				self.message_queue.put(('info','port_json',json.dumps(self.port_mode_info))) # , indent=4

			BLE_Device.dp("Port interrogation complete!")

	def _decode_port_mode_info(self, bt_message):

		if 'requests_until_complete' in self.port_mode_info:
			if self.port_mode_info['requests_until_complete'] <= 0:
				BLE_Device.dp(f'WARN: Did not expect this mode info report, refusing to update: {bt_message["readable"]}')
				return

		readable =''
		port = bt_message['port']
		mode = bt_message['mode']

		if port in self.ports:
			device = self.ports[port]
			readable += device.name+' ('+str(port)+')'
		else:
			readable += 'Port ('+str(port)+')'

		readable += ' mode '+str(mode)

		# FIXME: Stuff all this in a structure and then dump it out
		if not mode in self.port_mode_info[port]:
			print(f'ERROR: MODE {mode} MISSING FOR PORT {port}: SHOULD HAVE BEEN SET in _decode_mode_info_and_interrogate. Dumping: {bt_message["readable"]}')
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

		# Mapping
		elif bt_message['mode_info_type'] == 0x5:
			#self.port_mode_info[port][mode]['mapping_readable'] = bt_message['readable']

			if bt_message['IN_mapping']:
				self.port_mode_info[port][mode]['input_mappable'] = bt_message['IN_maptype']
			else:
				if bt_message['IN_maptype']:
					self.port_mode_info[port][mode]['not_input_mappable'] = bt_message['IN_maptype']

			if bt_message['OUT_mapping']:
				self.port_mode_info[port][mode]['output_mappable'] = bt_message['OUT_maptype']
			else:
				if bt_message['OUT_maptype']:
					self.port_mode_info[port][mode]['not_output_mappable'] = bt_message['OUT_maptype']


			if bt_message['IN_nullable']:
				self.port_mode_info[port][mode]['input_nullable'] = True
			if bt_message['OUT_nullable']:
				self.port_mode_info[port][mode]['output_nullable'] = True

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
			BLE_Device.dp('PMI Decoded:'+ readable)
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

	def _decode_hub_action(self, bt_message):
		BLE_Device.dp(self.system_type+" "+bt_message['action_str'],2)
		# Decoder.hub_action_type
		if bt_message['action'] == 0x30:
			self.message_queue.put(('event','power','turned_off'))
			# FIXME: Should we flag the device as disconnected here?  Has a message _ever_ come in AFTER this?
		elif bt_message['action'] == 0x31:
			self.message_queue.put(('event','bt','disconnected'))
		else:
			BLE_Device.dp(self.system_type+" unknown hub action "+hex(bt_message['action']),1)

	def _decode_hardware_network_command(self, bt_message):
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

	# ---- Random stuff ----

	# FIXME: Stop doing this and use logging
	def dp(pstr, level=1):
		if BLE_Device.DEBUG:
			if BLE_Device.DEBUG >= level:
				print(pstr)

	# ---- Bluetooth port writes for mortals ----
	async def interrogate_ports(self):
		if self.port_mode_info['requests_until_complete'] == 0:
			BLE_Device.dp("Starting port interrogation...")
			self._reset_port_mode_info()
			for port in self.ports:
				# This should be done as some kind of batch, blocking operation
				self.port_mode_info['requests_until_complete'] += 1

				await self._write_port_info_request(port, 0x1)
				await asyncio.sleep(0.2)
		else:
			print(f"ERROR: Refusing to start a second port interrogation until the first one is complete. Currently waiting for {self.port_mode_info['requests_until_complete']} requests to complete")

	async def turn_off(self):
		name_update_bytes = bytearray([
			0x04,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x2,	# 'hub_actions'
			0x1		# Decoder.hub_action_type: 'Switch Off Hub'  (Don't use 0x2f, powers down as if you yanked the battery)
		])
		await self._gatt_send(name_update_bytes)

	# Send any attached devices a message to process (or a specific device on a port)
	async def send_device_message(self, devtype, message, port=None):
		target_devs = []
		for attached_port in self.ports:
			dev = self.ports[attached_port]
			if dev.status != 0x0:		# Decoder.io_event_type_str[0x0]
				if dev.port_id == devtype:
					target_devs.append(dev)
			else:
				pass
				print("Attempted message {message} to disconnected device on port {port}")

		for dev in target_devs:
			if port is not None:
				if dev.port == port:
					BLE_Device.dp(f'SENDING {message} TO SPECIFIC PORT {port}',2)
					await dev.send_message(message, self.gatt_writer )
			else:
				BLE_Device.dp(f'SENDING {message}',2)
				await dev.send_message(message, self.gatt_writer )

	async def send_property_message(self, property_type_int, message):
		if property_type_int in Decoder.hub_property_str:
			if property_type_int in self.properties:
				target_property = self.properties[property_type_int]
				if len(message) == 2:
					if message[0] == 'set':
						payload = target_property.gatt_payload_for_property_set(message[1])
						if payload:
							await self._gatt_send(payload)
					elif message[0] == 'get':
						payload = target_property.gatt_payload_for_property_value_fetch()
						if payload:
							await self._gatt_send(payload)
					elif message[0] == 'subscribe':
						payload = target_property.gatt_payload_for_subscribe(message[1])
						if payload:
							if message[1]:
								target_property.subscribed = True
							else:
								target_property.subscribed = False

							await self._gatt_send(payload)
					else:
						BLE_Device.dp(f"Invalid command ({message[0]}) to {target_property.name}")
				else:
					BLE_Device.dp(f"Invalid message to {target_property.name}: {message}")
			else:
				BLE_Device.dp(f"Property doesn\'t exist for {property_type_int}: Message {message} failed.")
		else:
			BLE_Device.dp(f"Didn't find property {property_type_int} for message {message}")

	async def _gatt_send(self, payload):
		if self.connected:
			BLE_Device.dp("GATT SEND: "+" ".join(hex(n) for n in payload), 3)
			await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
			await asyncio.sleep(self.gatt_send_rate_limit)
			return True
		else:
			BLE_Device.dp("GATT SEND PROHIBITED: NOT CONNECTED", 3)
			return False

	# ---- Bluetooth port writes for the class ----

	async def _write_port_mode_info_request(self, port, mode, infotype):
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
		await self._gatt_send(payload)

	async def _write_port_info_request(self, port, mode_info):
		# 3.15.2
		# 0: Request port_value_single value
		# 1: Request port_info for port modes
		# 2: Request port_info for mode combinations
		mode_int = int(mode_info)
		if mode_int > 2 or mode_int < 0:
			return
		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x21,	# Command: port_info_req
			# end header
			port,
			mode_int
		])
		payload[0] = len(payload)
		await self._gatt_send(payload)
