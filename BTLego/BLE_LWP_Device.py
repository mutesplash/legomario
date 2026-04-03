import asyncio
import uuid
import logging
from queue import SimpleQueue
from collections.abc import Iterable

import datetime
import json

from bleak import BleakClient

from .Decoder import Decoder, HProp

from .LPF_Devices import *
from .LPF_Devices.LPF_Device import generate_valid_lpf_message_types

from .HubProperty import HubProperty
from .HubPort import HubPort
from .HubPortModeInfo import HubPortModeInfo

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

	def __init__(self, advertisement_data=None, shortname=''):

		self.lpf_message_types = generate_valid_lpf_message_types()

		super().__init__(advertisement_data, shortname)

		self.mode_probe_rate_limit = 0.3

		# LWP
		self.characteristic_uuid = '00001624-1212-efde-1623-785feabcd123'
		self.hub_service_uuid = '00001623-1212-efde-1623-785feabcd123'
		self.packet_decoder = Decoder.decode_payload

		# Override in subclass __init__ and set to a list of hex values for
		# Mode Information Types over which the device throws errors when doing
		# port mode information requests ( interrogate_ports() )
		self.mode_probe_ignored_info_types = ()

		self.watchdogs = {
			'port_info_request': None,
			'device_init': None
		}

		self.minimum_attached_ports = 0

		self.ports = {}
		self.properties = {}

		self._init_hub_properties()

	def _init_hub_properties(self):
		for property_int in Decoder.hub_property_str:
			if Decoder.hub_property_str[property_int] not in self.device_property_exclusion_str:
				self.properties[property_int] = HubProperty(property_int)

	# override: Keep track of how long it takes to track all the device inits
	async def connect(self, device):
		await super().connect(device)
		self.watchdogs['device_init'] = datetime.datetime.now()

	def _init_port_data(self, bt_message):

		port = bt_message['port']
		if not port in self.ports:
			self.ports[port] = HubPort(port)
			self.ports[port].set_parent_info(self.__class__.__name__, self.shortname)
			self.ports[port].mode_probe_ignored_info_types = self.mode_probe_ignored_info_types

		port_id = bt_message['io_type_id']
		port_classname = LPF_class_for_type_id(port_id)
		retval = False
		if port_classname:
			# https://stackoverflow.com/a/547867
			port_module = __import__('BTLego.LPF_Devices.'+port_classname, fromlist=[port_classname])
			port_classobj = getattr(port_module, port_classname)
			attaching_device = port_classobj()

			if port_classname == 'LPF_Device':
				self.logger.warning(f'Class {self.__class__.__name__} contains device type id {port_id} ({attaching_device.name}) on port {port} that has no class handler')

			attaching_device.port = port
			attaching_device.port_id = port_id
			attaching_device.hw_ver_str = bt_message['hw_ver_str']
			attaching_device.fw_ver_str = bt_message['sw_ver_str']
			if port_id in Decoder.io_type_id_str:
				attaching_device.name = Decoder.io_type_id_str[port_id]
			else:
				self.logger.error(f'Previously unknown port identifier {port_id} on device {self.__class__.__name__}')
				attaching_device.name = f"UNKNOWN_DEV_ON_PORT_{port_id}"

			attaching_device.status = 0x1		# Decoder.io_event_type_str[0x1]
			for message_type, sub_count in self.BLE_event_subscriptions.items():
				if sub_count > 0:
					attaching_device.subscribe_to_messages(message_type, True, self.gatt_writer)
					# On init, don't have to unsub

			self.ports[port].attach_device(attaching_device)

			# FIXME: Ah, this is fun:  On hub4, Voltage, RGB and Current are laggards so this returns too early
			self.message_queue.put(('device_ready', port_id, port))
			retval = True
		else:
			self.logger.warning(f'Class {self.__class__.__name__} contains unknown device type id {port_id} on port {port}')

		if len(self.ports) == self.minimum_attached_ports:
			self.watchdogs['device_init'] = None
			self.message_queue.put(('info','initialized',('minimum_connected_ports', len(self.ports))))
			self._inital_connect_updates()
		return retval

	def _detach_lpf_device(self,port):
		if port in self.ports:
			self.ports[port].detach_device()
			del self.ports[port]

	def _reset_port_mode_info(self):
		for port in list(self.ports):
			self.ports[port].reset_mode_info()

	def _generate_port_info_dict(self):
		port_mode_info = {}
		port_mode_info['port_count'] = len(self.ports)
		for port in self.ports:
			port_mode_info[port] = self.ports[port].dump_info()
		return port_mode_info

	# Overrideable
	def _inital_connect_updates(self):

		# Signal connect finished
		self.message_queue.put(('info','player',self.shortname))
		# Replace the above signal with something more accurate
		self.message_queue.put(('info','connected',self.shortname))

	# Override in subclass and call super if you subclass to initialize BLE_event_subscriptions with all available message types
	def _reset_event_subscription_counters(self):
		super()._reset_event_subscription_counters()
		for message_type in self.message_types:
			self.BLE_event_subscriptions[message_type] = 0;
		for message_type in self.lpf_message_types:
			self.BLE_event_subscriptions[message_type] = 0;

	# ---- Things Normal People Can Do ----
	# (Not really all of them, there are some direct bluetooth things below)

	def dump_status(self):
		super().dump_status()
		self.logger.info("PORT LIST\n")
		for port in self.ports:
			dev = self.ports[port].attached_device
			self.logger.info(f'\tPort {dev.port} {dev.name} : {dev.devtype} {dev.mode_subs} HW:{dev.hw_ver_str} FW:{dev.fw_ver_str}')
		self.logger.info("PROPERTY LIST\n")
		for prop_int, propobj in self.properties.items():
			self.logger.info(f'\tProperty {propobj.name} ({propobj.reference_number}) Subscribed: {propobj.subscribed}')
		self.logger.info(f"PORT MODE INFO\n{json.dumps(self._generate_port_info_dict(), indent=4)}")

	# ---- Message processing ----

	# Checks all Properties and Ports for LPF devices that handle the given message_type
	# Subscribes or unsubscribes to these messages as requested
	def _set_hardware_subscription(self, message_type, should_subscribe=True):

		if not message_type in self.BLE_event_subscriptions:
			self.logger.debug(f'No known devices generate {message_type}')
			return False

		for port in self.ports:
			self.ports[port].attached_device.subscribe_to_messages(message_type, should_subscribe, self.gatt_writer)
		return True

	# FIXME: Dead code path?
	def _set_property_subscription(self, property_int, should_subscribe=True):
		if property_int in self.properties:
			payload = self.properties[property_int].gatt_payload_for_subscribe(should_subscribe)
			if payload:
				self._gatt_send(payload)
		else:
			self.logger.error(f'{self.shortname} does not have a property numbered {property_int}')

	# Returns false if unprocessed
	# Override in subclass, call super if you don't process the bluetooth message type
	async def _process_bt_message(self, bt_message):
		msg_prefix = self.shortname+" "

		if self.watchdogs['port_info_request']:
			if (self.watchdogs['port_info_request'] +  + datetime.timedelta(seconds=10)) < datetime.datetime.now():
				self.logger.error(f'{self.shortname} mode info request watchdog timeout!')
				self.watchdogs['port_info_request'] = None
				self.message_queue.put(('error','message',f"Mode info requests were still outstanding when watchdog timed out"))
				if self.logger.isEnabledFor(logging.DEBUG):
					self.dump_status()

		if self.watchdogs['device_init']:
			if (self.watchdogs['device_init']  + datetime.timedelta(seconds=10)) < datetime.datetime.now():
				self.logger.error(f'{self.shortname} mode info request device_watchdog timeout.  Assuming device enumeration complete and signaling such')
				self.watchdogs['device_init'] = None
				self.message_queue.put(('info','initialized',('minimum_connected_ports', len(self.ports))))
				self._inital_connect_updates()

		if Decoder.message_type_str[bt_message['type']] == 'port_input_format_single':
			if self.logger.isEnabledFor(logging.DEBUG):
				msg = "Disabled notifications on "
				if bt_message['notifications']:
					# Returned typically after gatt write
					msg = "Enabled notifications on "

				port_text = "port "+str(bt_message['port'])

				if bt_message['port'] in self.ports:
					port = bt_message['port']
					device = self.ports[port].attached_device
					port_text = f"{device.name} port ({port})"

				self.logger.debug(msg_prefix+msg+port_text+", mode "+str(bt_message['mode']))

		# Sent on connect, without request
		elif Decoder.message_type_str[bt_message['type']] == 'hub_attached_io':
			event = Decoder.io_event_type_str[bt_message['event']]

			port = -1
			if bt_message['port'] in self.ports:
				port = bt_message['port']

			if event == 'attached':
				dev = "UNKNOWN DEVICE"
				if bt_message['io_type_id'] in Decoder.io_type_id_str:
					dev = Decoder.io_type_id_str[bt_message['io_type_id']]
				else:
					dev += "_"+str(bt_message['io_type_id'])

				if port != -1:
					self.logger.info(msg_prefix+"Re-attached "+dev+" on port "+str(bt_message['port']))
					device = self.ports[port].attached_device
					device.status = bt_message['event']
				else:
					self.logger.info(msg_prefix+"Attached "+dev+" on port "+str(bt_message['port']))
					# Can't mess with the port list outside of the drain lock
					async with self.drain_lock:
						if not self._init_port_data(bt_message):
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
				port = bt_message['port']
				device = self.ports[port].attached_device
				if device:
					if port != device.port:
						self.logger.error(f"CONSISTENCY ERROR: DEVICE ON PORT {port} NOT EQUAL TO PORT {device.port} IN CLASS")
						# FIXME: Harsh?
						quit()

					message = device.decode_pvs(port, bt_message['value'])
					if message is None:
						if self.TRACE:
							self.logger.debug(f'{msg_prefix} {device.name} ({device.__class__.__name__}) declared NO-OP for PVS:'+bt_message['readable'])
					else:
						if len(message) == 3:
							if message[0] != 'noop':
								self.message_queue.put(message)
						elif len(message) == 2 or len(message) > 3:
							self.logger.error(f'{msg_prefix}{message[0]} on {device.name} port {port} missing key & value while processing PVS:{message[1]}')
						else:
							self.logger.error(f'{msg_prefix} {device.name} FAILED TO DECODE PVS DATA ON PORT {port}:'+" ".join(hex(n) for n in bt_message['value']))
				else:
					self.logger.error(f'{msg_prefix} Received data for unconfigured port {port}:'+bt_message['readable'])
			else:
				self.logger.error(f'{msg_prefix} No idea what kind of PVS:{port}')

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

			port = bt_message['port']
			if port in self.ports:
				self.ports[port].process_port_info_message(bt_message, self._gatt_send)
			else:
				self.logger.error(f"{msg_prefix} RECIEVED PORT INFO MESSAGE FOR PORT THAT DOESN'T EXIST: {bt_message['readable']}")

		elif Decoder.message_type_str[bt_message['type']] == 'port_mode_info':
			# Debug stuff for the ports and modes, similar to list command on BuildHAT
			self.watchdogs['port_info_request'] = datetime.datetime.now()

			port = bt_message['port']
			mode = bt_message['mode']

			if port in self.ports:
				if mode in self.ports[port].reported.modes:
					self.ports[port].reported.modes[mode].process_mode_info_request(bt_message)
				else:
					self.logger.error(f"ERROR: No mode ({mode}) on port ({port}) exists for port info message: {bt_message['readable']}")
			else:
				self.logger.error(f"ERROR: No port ({port}) exists for port info message: {bt_message['readable']}")

			incomplete_ports = len(self.ports)
			for port in self.ports:
				if self.ports[port].check_probe_completion():
					incomplete_ports -= 1
#					print(f"DONE WITH PORT {port} ({incomplete_ports} left)")

			if incomplete_ports == 0:
				self.watchdogs['port_info_request'] = None

				self.message_queue.put(('info','port_json',json.dumps(self._generate_port_info_dict())))
				self.logger.info("Port interrogation complete!")

		elif Decoder.message_type_str[bt_message['type']] == 'hw_network_cmd':
			self._decode_hardware_network_command(bt_message)

		else:
			return False

		return True

	# Override if you wanna decode a property to send _additional_ messages
	def _decode_property(self, prop_id, value):
		pass

	def _decode_hub_action(self, bt_message):
		self.logger.debug(self.shortname+" "+bt_message['action_str'])
		# Decoder.hub_action_type
		if bt_message['action'] == 0x30:
			self.message_queue.put(('event','power','turned_off'))
			# FIXME: Should we flag the device as disconnected here?  Has a message _ever_ come in AFTER this?
		elif bt_message['action'] == 0x31:
			self.message_queue.put(('event','bt','disconnected'))
		else:
			self.logger.warning(self.shortname+" unknown hub action "+hex(bt_message['action']))

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
				self.logger.warning(self.shortname+" unknown hw command: "+bt_message['readable'])
		else:
			self.logger.error(self.shortname+" Apparently not a hw network command?:"+bt_message['readable'])

	# ---- Bluetooth port writes for mortals ----
	def interrogate_ports(self):

		start = False
		outstanding_probe_requests = 0
		for port in self.ports:
			outstanding_probe_requests += self.ports[port].mode_probe_count()

		if outstanding_probe_requests == 0:
			if self.ports[port].mode_probes_running:
				self.logger.error("ERROR: All modes report no outstanding requests but device thinks mode probes are still running")
			start = True

		if start:
			self.logger.info("Starting port interrogation...")
			self._reset_port_mode_info()

			self.watchdogs['port_info_request'] = datetime.datetime.now()

			for port in self.ports:
				self.logger.warning(f"{self.shortname} Requesting info for port {port} ...")
				self.ports[port].request_port_info(self._gatt_send)

		else:
			self.logger.error(f"Refusing to start a second port interrogation until the first one is complete. Currently waiting for {outstanding_probe_requests} requests to complete")

	def turn_off(self):
		name_update_bytes = bytearray([
			0x04,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x2,	# 'hub_actions'
			0x1		# Decoder.hub_action_type: 'Switch Off Hub'  (Don't use 0x2f, powers down as if you yanked the battery)
		])
		self._gatt_send(name_update_bytes)

	# Send any attached devices a message to process (or a specific device on a port)
	def send_device_message(self, devtype, message, port=None):

		target_devs = []
		for attached_port in self.ports:
			dev = self.ports[attached_port].attached_device
			if dev.status != 0x0:		# Decoder.io_event_type_str[0x0]
				if dev.port_id == devtype:
					target_devs.append(dev)
			else:
				self.logger.warning("Attempted message {message} to disconnected device on port {port}")

		for dev in target_devs:
			if port is not None:
				if dev.port == port:
					self.logger.debug(f'SENDING {message} TO SPECIFIC PORT {port} ON DEVICE {dev.name}')
					dev.send_message(message, self.gatt_writer)
			else:
				self.logger.debug(f'SENDING {message} TO DEVICE {dev.name}')
				dev.send_message(message, self.gatt_writer)

	def send_property_message(self, property_type_int, message):
		if property_type_int in Decoder.hub_property_str:
			if property_type_int in self.properties:
				target_property = self.properties[property_type_int]
				if len(message) == 2:
					if message[0] == 'set':
						payload = target_property.gatt_payload_for_property_set(message[1])
						if payload:
							self._gatt_send(payload)
					elif message[0] == 'get':
						payload = target_property.gatt_payload_for_property_value_fetch()
						if payload:
							self._gatt_send(payload)
					elif message[0] == 'subscribe':
						payload = target_property.gatt_payload_for_subscribe(message[1])
						if payload:
							if message[1]:
								target_property.subscribed = True
							else:
								target_property.subscribed = False
							self._gatt_send(payload)
					else:
						self.logger.error(f"Invalid command ({message[0]}) to {target_property.name}")
				else:
					self.logger.error(f"Invalid message to {target_property.name}: {message}")
			else:
				self.logger.error(f"Property doesn\'t exist for {property_type_int}: Message {message} failed.")
		else:
			self.logger.error(f"Didn't find property {property_type_int} for message {message}")
