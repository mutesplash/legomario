import asyncio
import uuid
import logging
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .Decoder import Decoder, HProp

from .LPF_Devices import *
from .LPF_Devices.LPF_Device import generate_valid_lpf_message_types

from .HubProperty import HubProperty

from .BLE_Device import BLE_Device

class BLE_LWP_Device(BLE_Device):

	# If there was a level five... unfortunately, too complicated to bother implementing
	TRACE = False

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

	device_property_exclusion_str = (
		'Mario Volume',
	)

	# ok, but what is service ID F000FFC0-0451-4000-B000-000000000000 with the
	# following characteristic IDs for LEGO Mario?
	# FOTA?  OAD Service? Texas Instruments OTA firmware download?
	# https://software-dl.ti.com/lprf/simplelink_cc2640r2_latest/docs/blestack/ble_user_guide/html/oad-ble-stack-3.x/oad_profile.html
	# https://software-dl.ti.com/lprf/sdg-latest/html/oad-ble-stack-3.x/oad.html
	# F000FFC1-0451-4000-B000-000000000000
	# F000FFC2-0451-4000-B000-000000000000
	# F000FFC5-0451-4000-B000-000000000000

	# ---- Initializations, obviously ----

	def __init__(self, advertisement_data=None):

		self.lpf_message_types = generate_valid_lpf_message_types()

		super().__init__(advertisement_data)

		self.mode_probe_rate_limit = 0.3

		# LWP
		self.characteristic_uuid = '00001624-1212-efde-1623-785feabcd123'
		self.hub_service_uuid = '00001623-1212-efde-1623-785feabcd123'
		self.packet_decoder = Decoder.decode_payload

		# Override in subclass __init__ and set to a list of hex values for
		# Mode Information Types over which the device throws errors when doing
		# port mode information requests ( interrogate_ports() )
		self.mode_probe_ignored_info_types = ()

		self.port_mode_info = {
			'port_count':0,
			'requests_until_complete':0		# Port interrogation
		}

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
			if port_id in Decoder.io_type_id_str:
				self.ports[port].name = Decoder.io_type_id_str[port_id]
			else:
				self.logger.error(f'Previously unknown port identifier {port_id} on device {self.__class__.__name__}')
				self.ports[port].name = f"UNKNOWN_DEV_ON_PORT_{port_id}"
			self.ports[port].status = 0x1		# Decoder.io_event_type_str[0x1]
			for message_type, sub_count in self.BLE_event_subscriptions.items():
				if sub_count > 0:
					await self.ports[port].subscribe_to_messages(message_type, True, self.gatt_writer)
					# On init, don't have to unsub

			if port_classname == 'LPF_Device':
				devname = self.ports[port].name
				self.logger.warning(f'Class {self.__class__.__name__} contains device type id {port_id} ({devname}) on port {port} that has no class handler')

			# FIXME: Ah, this is fun:  On hub4, Voltage, RGB and Current are laggards so this returns too early
			self.message_queue.put(('device_ready', port_id, port))
			return True
		else:
			self.logger.warning(f'Class {self.__class__.__name__} contains unknown device type id {port_id} on port {port}')
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
		super()._reset_event_subscription_counters()
		for message_type in self.message_types:
			self.BLE_event_subscriptions[message_type] = 0;
		for message_type in self.lpf_message_types:
			self.BLE_event_subscriptions[message_type] = 0;

	# ---- Things Normal People Can Do ----
	# (Not really all of them, there are some direct bluetooth things below)

	async def dump_status(self):
		await super().dump_status()
		self.logger.info("PORT LIST\n")
		for port in self.ports:
			dev = self.ports[port]
			self.logger.info(f'\tPort {dev.port} {dev.name} : {dev.devtype} {dev.mode_subs} HW:{dev.hw_ver_str} FW:{dev.fw_ver_str}')
		self.logger.info("PROPERTY LIST\n")
		for prop_int, propobj in self.properties.items():
			self.logger.info(f'\tProperty {propobj.name} ({propobj.reference_number}) Subscribed: {propobj.subscribed}')
		self.logger.info("PORT MODE INFO\n"+json.dumps(self.port_mode_info, indent=4))

	# ---- Message processing ----

	# Checks all Properties and Ports for LPF devices that handle the given message_type
	# Subscribes or unsubscribes to these messages as requested
	async def _set_hardware_subscription(self, message_type, should_subscribe=True):

		if not message_type in self.BLE_event_subscriptions:
			self.logger.debug(f'No known devices generate {message_type}')
			return False

		for port in self.ports:
			await self.ports[port].subscribe_to_messages(message_type, should_subscribe, self.gatt_writer)
		return True

	# FIXME: Dead code path?
	async def _set_property_subscription(self, property_int, should_subscribe=True):
		if property_int in self.properties:
			payload = self.properties[property_int].gatt_payload_for_subscribe(should_subscribe)
			if payload:
				await self._gatt_send(payload)
		else:
			self.logger.error(f'{self.system_type} does not have a property numbered {property_int}')

	# Returns false if unprocessed
	# Override in subclass, call super if you don't process the bluetooth message type
	async def _process_bt_message(self, bt_message):
		msg_prefix = self.system_type+" "

		if Decoder.message_type_str[bt_message['type']] == 'port_input_format_single':
			if self.logger.isEnabledFor(logging.DEBUG):
				msg = "Disabled notifications on "
				if bt_message['notifications']:
					# Returned typically after gatt write
					msg = "Enabled notifications on "

				port_text = "port "+str(bt_message['port'])

				if bt_message['port'] in self.ports:
					port_text = self.ports[bt_message['port']].name+" port ("+str(bt_message['port'])+")"

				self.logger.debug(msg_prefix+msg+port_text+", mode "+str(bt_message['mode']))

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
					self.logger.info(msg_prefix+"Re-attached "+dev+" on port "+str(bt_message['port']))
					self.ports[reattached].status = bt_message['event']
				else:
					self.logger.info(msg_prefix+"Attached "+dev+" on port "+str(bt_message['port']))
					# Can't mess with the port list outside of the drain lock
					async with self.drain_lock:
						if not await self._init_port_data(bt_message):
							if bt_message['io_type_id'] in Decoder.io_type_id_str:
								self.logger.warning(msg_prefix+" NO CLASS EXISTS FOR LPF ATTACHED DEVICE "+Decoder.io_type_id_str[bt_message['io_type_id']]+": "+str(bt_message['readable']))
							else:
								self.logger.warning(msg_prefix+" TOTALLY UNKNOWN DEVICE "+str(bt_message['io_type_id'])+": "+str(bt_message['readable']))

			elif event == 'detached':
				self.logger.info(msg_prefix+"Detached device on port "+str(bt_message['port']))
				self._detach_lpf_device(bt_message['port'])

			else:
				self.logger.info(msg_prefix+"HubAttachedIO: "+bt_message['readable'])

		elif Decoder.message_type_str[bt_message['type']] == 'port_value_single':

			device = None
			if bt_message['port'] in self.ports:
				device = self.ports[bt_message['port']]
				if device:
					if bt_message['port'] != device.port:
						self.logger.error("CONSISTENCY ERROR: DEVICE ON PORT "+str(bt_message['port'])+f" NOT EQUAL TO PORT {device.port} IN CLASS ")
						# FIXME: Harsh?
						quit()

					message = device.decode_pvs(bt_message['port'], bt_message['value'])
					if message is None:
						if self.TRACE:
							self.logger.debug(f'{msg_prefix} {device.name} ({device.__class__.__name__}) declared NO-OP for PVS:'+bt_message['readable'])
					else:
						if len(message) == 3:
							if message[0] != 'noop':
								self.message_queue.put(message)
						elif len(message) == 2 or len(message) > 3:
							self.logger.error(f'{msg_prefix}{message[0]} on {device.name} port '+str(bt_message['port'])+f' missing key & value while processing PVS:{message[1]}')
						else:
							self.logger.error(f'{msg_prefix} {device.name} FAILED TO DECODE PVS DATA ON PORT '+str(bt_message['port'])+":"+" ".join(hex(n) for n in bt_message['value']))
				else:
					self.logger.error(f'{msg_prefix} Received data for unconfigured port '+str(bt_message['port'])+':'+bt_message['readable'])
			else:
				self.logger.error(f'{msg_prefix} No idea what kind of PVS:'+bt_message['readable'])

		elif Decoder.message_type_str[bt_message['type']] == 'hub_properties':
			if not Decoder.hub_property_op_str[bt_message['operation']] == 'Update':
				# everything else is a write, so you shouldn't be getting these messages!
				self.logger.error(msg_prefix+"THIS CLIENT DOES NOT UPDATE YET THIS MESSAGE EXISTS: "+bt_message['readable'])

			else:
				if not bt_message['property'] in Decoder.hub_property_str:
					self.logger.warning(msg_prefix+"Unknown property "+bt_message['readable'])
				else:
					prop_id = bt_message['property']
					self._decode_property(prop_id, bt_message['value'])
					self.message_queue.put( ('property', prop_id, bt_message['value']) )

		elif Decoder.message_type_str[bt_message['type']] == 'port_output_command_feedback':
			# Don't really care about these messages?  Just a bunch of queue status reporting
			if self.TRACE:
				self.logger.debug(msg_prefix+" "+bt_message['readable'])

		elif Decoder.message_type_str[bt_message['type']] == 'hub_alerts':
			# Ignore "status OK" messages
			if bt_message['status'] == True:
				self.logger.info(msg_prefix+"ALERT! "+bt_message['alert_type_str']+" - "+bt_message['operation_str'])
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
			if 'mode_combinations' in bt_message and port in self.port_mode_info:
				self.port_mode_info[port]['combinations'] = bt_message['mode_combinations']
			else:
				self.logger.error(f'Mode combinations NOT DECODED: {bt_message["readable"]}')
			return
		else:
			self.logger.debug(f"Interrogating mode info for {bt_message['num_modes']} modes on port {port}: {device.name}")

		if 'requests_until_complete' in self.port_mode_info:
			if self.port_mode_info['requests_until_complete'] <= 0:
				self.logger.warning(f'WARN: Did not expect this mode info description, refusing to update: {bt_message["readable"]}')
				return

		if not port in self.port_mode_info:
			self.port_mode_info[port] = {}

		self.port_mode_info[port]['mode_count'] = bt_message['num_modes']
		self.port_mode_info[port]['name'] = device.name
		self.port_mode_info[port]['attached_port'] = port
		self.port_mode_info[port]['port_id'] = device.port_id
		self.port_mode_info[port]['port_class'] = device.__class__.__name__
		self.port_mode_info[port]['parent_hub_driver'] = self.__class__.__name__
		self.port_mode_info[port]['parent_type'] = self.system_type
		self.port_mode_info[port]['hw'] = self.ports[port].hw_ver_str
		self.port_mode_info[port]['fw'] = self.ports[port].fw_ver_str
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

				# If the BLE_Device supports motor bias, only enable on approved LPF devices
				if 0x7 in self.port_mode_info[port][mode]['requests_outstanding']:
					if not device.port_id in LPF_Device.motor_bias_device_allowlist:
						del self.port_mode_info[port][mode]['requests_outstanding'][0x7]

			frozen_requests = list(self.port_mode_info[port][mode]['requests_outstanding'].items())
			for hexkey, requested in frozen_requests:
				if requested:
#					self.logger.debug(f'\tRequest {direction} port {port} info for mode {mode} key {hexkey}')

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
				self.logger.info(f'DUMPING INCOMPLETE PORT JSON: {json.dumps(self.port_mode_info)}')
			else:
				self.message_queue.put(('info','port_json',json.dumps(self.port_mode_info))) # , indent=4

			self.logger.info("Port interrogation complete!")

	def _decode_port_mode_info(self, bt_message):

		if 'requests_until_complete' in self.port_mode_info:
			if self.port_mode_info['requests_until_complete'] <= 0:
				self.logger.warning(f'WARN: Did not expect this mode info report, refusing to update: {bt_message["readable"]}')
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
			self.logger.error(f'ERROR: MODE {mode} MISSING FOR PORT {port}: SHOULD HAVE BEEN SET in _decode_mode_info_and_interrogate. Dumping: {bt_message["readable"]}\nKeys:\n'+str(self.port_mode_info[port].keys()))
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

		if not decoded:
			self.logger.warning(f'No decoder for this: {readable}')
		else:
			self.logger.debug(f'PMI Decoded: {readable}')

		if 'requests_outstanding' in self.port_mode_info[port][mode]:
			if bt_message['mode_info_type'] in self.port_mode_info[port][mode]['requests_outstanding']:
				self.port_mode_info[port][mode]['requests_outstanding'].pop(bt_message['mode_info_type'],None)
			else:
				self.logger.warning("DUPLICATE mode info type "+hex(bt_message['mode_info_type'])+' on port '+str(port)+' mode '+str(mode))

			# Remove requests_outstanding if zero outstanding (and all the modes with it)
			if not self.port_mode_info[port][mode]['requests_outstanding']:
				self.port_mode_info[port][mode].pop('requests_outstanding',None)
				if mode in self.port_mode_info[port]['mode_info_requests_outstanding']:
					self.port_mode_info[port]['mode_info_requests_outstanding'].pop(mode,None)

		else:
			self.logger.warning(f"EXTRA mode info type {hex(bt_message['mode_info_type'])} on port {port} mode {mode} DUMP:{bt_message['readable']}")

	def _decode_hub_action(self, bt_message):
		self.logger.debug(self.system_type+" "+bt_message['action_str'])
		# Decoder.hub_action_type
		if bt_message['action'] == 0x30:
			self.message_queue.put(('event','power','turned_off'))
			# FIXME: Should we flag the device as disconnected here?  Has a message _ever_ come in AFTER this?
		elif bt_message['action'] == 0x31:
			self.message_queue.put(('event','bt','disconnected'))
		else:
			self.logger.warning(self.system_type+" unknown hub action "+hex(bt_message['action']))

	def _decode_hardware_network_command(self, bt_message):
		if 'command' in bt_message:
			if bt_message['command'] == 'connection_request':
				message = None
				if bt_message['value'] == 'button_up':
					message = ('connection_request','button','up')
				elif bt_message['value'] == 'button_down':
					message = ('connection_request','button','down')
				self.message_queue.put(message)
			elif bt_message['command'] == 'family_request':
				# This module isn't going to send you one for now, so... ignore it
				message = ('family_request','please_send','new_family_if_there_is_one')
				self.message_queue.put(message)
			else:
				self.logger.warning(self.system_type+" unknown hw command: "+bt_message['readable'])
		else:
			self.logger.error(self.system_type+" Apparently not a hw network command?:"+bt_message['readable'])

	# ---- Bluetooth port writes for mortals ----
	async def interrogate_ports(self):
		start = False
		if 'requests_until_complete' in self.port_mode_info:
			if self.port_mode_info['requests_until_complete'] == 0:
				start = True
		else:
			start = True

		if start:
			self.logger.info("Starting port interrogation...")
			self._reset_port_mode_info()
			for port in self.ports:
				# This should be done as some kind of batch, blocking operation
				self.port_mode_info['requests_until_complete'] += 1

				await self._write_port_info_request(port, 0x1)
				await asyncio.sleep(mode_probe_rate_limit)
		else:
			self.logger.error(f"Refusing to start a second port interrogation until the first one is complete. Currently waiting for {self.port_mode_info['requests_until_complete']} requests to complete")

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
				self.logger.warning("Attempted message {message} to disconnected device on port {port}")

		for dev in target_devs:
			if port is not None:
				if dev.port == port:
					self.logger.debug(f'SENDING {message} TO SPECIFIC PORT {port} ON DEVICE {dev.name}')
					await dev.send_message(message, self.gatt_writer )
			else:
				self.logger.debug(f'SENDING {message} TO DEVICE {dev.name}')
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
						self.logger.error(f"Invalid command ({message[0]}) to {target_property.name}")
				else:
					self.logger.error(f"Invalid message to {target_property.name}: {message}")
			else:
				self.logger.error(f"Property doesn\'t exist for {property_type_int}: Message {message} failed.")
		else:
			self.logger.error(f"Didn't find property {property_type_int} for message {message}")

	# ---- Bluetooth port writes for the class ----

	async def _write_port_mode_info_request(self, port, mode, infotype):
		if mode < 0 or mode > 255:
			self.logger.error('Invalid mode '+str(mode)+' for mode info request')
			return
		if not infotype in Decoder.mode_info_type_str:
			self.logger.error('Invalid information type '+hex(infotype)+' for mode info request')
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
