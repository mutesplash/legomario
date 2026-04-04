import asyncio
import uuid
import logging
from queue import SimpleQueue
from collections.abc import Iterable

import datetime
import json

from bleak import BleakClient

from .Decoder import Decoder

from .BLE_Device import BLE_Device

from .LPF_Devices import *
from .LPF_Devices.LPF_Device import generate_valid_lpf_message_types

from .HubPort import HubPort


class BLE_WeDo(BLE_Device):

	# If there was a level five... unfortunately, too complicated to bother implementing
	TRACE = True

	def __init__(self, advertisement_data=None, shortname=''):
		super().__init__(advertisement_data, shortname)

		# Don't think this _can_ probe?
		self.mode_probe_ignored_info_types = ()

		self.watchdogs = {
			'port_info_request': None,
			'device_init': None
		}

		# WeDo2
		# Thanks pybricks
		# https://github.com/pybricks/technical-info/blob/master/assigned-numbers.md
		#hub_service = '00001523-1212-efde-1523-785feabcd123'
			#name_characteristic = '00001524-1212-efde-1523-785feabcd123'	R/W
			#button_state_ = '00001526-1212-efde-1523-785feabcd123'			R/N
		self.hub_attached_io_ = '00001527-1212-efde-1523-785feabcd123'

			#low_volt_alert_ = '00001528-1212-efde-1523-785feabcd123'
			#high_current_alert_ = '00001529-1212-efde-1523-785feabcd123'
			#low_signal_alert = '0000152a-1212-efde-1523-785feabcd123'
			#power_off_ = '0000152b-1212-efde-1523-785feabcd123'
			#port_vcc_control = '0000152c-1212-efde-1523-785feabcd123'
			#battery_type_ = '0000152d-1212-efde-1523-785feabcd123'
			#disconnect_ = '0000152e-1212-efde-1523-785feabcd123'

		# Standardized BT services
		#device_information_service = '0000180a-0000-1000-8000-00805f9b34fb'
			#firmware_rev_characteristic_uuid = '00002a26-0000-1000-8000-00805f9b34fb'
			#sw_rev_characteristic_uuid = '00002a28-0000-1000-8000-00805f9b34fb'
			#manuf_name_characteristic_uuid = '00002a29-0000-1000-8000-00805f9b34fb'

		#battery_service = '0000180f-0000-1000-8000-00805f9b34fb'	#org.bluetooth.service.battery_service
			#battery_level_characteristic_uuid = '00002a19-0000-1000-8000-00805f9b34fb'	Read, Notify

		#self.service_uuid = '00004f0e-1212-efde-1523-785feabcd123'			# WeDo2 Input service
		self.btle_uuid_sensor = '00001560-1212-EFDE-1523-785FEABCD123'	# Sensor Value, "input value" in SDK
				# (b'\x02\x06\x03') on first start_notify()
		self.btle_uuid_values = '00001561-1212-EFDE-1523-785FEABCD123'	# Value Format, "input format" in SDK
				# (b'\x02\x06\x17\x00\x01\x00\x00\x00\x00\x00\x01') on first start_notify()
				# SDK has no idea what to do with the above, but it sets them for notifications
				# See: Decoder FIXME: Probably useless duplicate here

		self.btle_uuid_input = '00001563-1212-EFDE-1523-785FEABCD123'	# Input command (same as SDK) (can't .start_notify())
				# Write stuff here to configure devices?
				# 0x1	Command ID (SDK name) (0: input value, 1: input format) (SDK never writes to command input value)
				# 0x2	Command Type (SDK name) (0: clear, 1: read, 2: write)
				# 0x1	Port Number (SDK name: Connect ID)
				# --- end LEInputCommand prefix and begin payload
				#22	Port ID (22 or Tilt sensor, 0x17: RGB built-in)
				#01	Absolute mode (0x0 indexed)
				#0x1 0x0 0x0 0x0	delta (value here: 1)
				#02 (SI format)
				#01 Notification Enable (0x0 disable)

		# Other people report using handle 0x3d (61)
		# But my hub didn't have 61, it had 60, which was identified by this UUID
		# Moral of the story, don't use handles, always UUIDs?

		self.btle_uuid_output = '00001565-1212-efde-1523-785feabcd123'	# Output command (same as SDK) (can't .start_notify())
			# bytearray([
			#	0x5,		Port Number (SDK name: Connect ID) (piezo: 5)
			#	0x2			Command (SDK name: Command ID) (play 2)
			#	0x4,		Payload length (bytes of everything below this)
			# ------- Example for Command 2 ----
			#	0xB8, 0x01,	Hz
			#	0xE8, 0x03	Milliseconds
			#])
			# Command IDs
			# 1: Motor power ( 1 byte )
			# 2: Play Piezo ( freqency, milliseconds: two 16-bit values )
			# 3: Stop Piezo ( no payload )
			# 4: Write RGB	( R, G, B: 3 bytes absolute, 1 byte indexed )
			# 5: Write Direct

			# len 4
			# 0x5 Port 5 (piezo)
			# 0x2 Command (play)
			#04B801E803

		self.characteristic_uuid = self.btle_uuid_input

		self.packet_decoder = Decoder.decode_wedo2_packet

		self.WeDo2_characteristic_subscriptions = {}

		self.ports = {}
		self.minimum_attached_ports = 4

	# Complete override base to change subs to notify uuids
	async def connect(self, device):
		async with self.lock:
			self.logger.info("Connecting to "+str(self.shortname)+"...")
			self.device = device
			try:
				self.client = BleakClient(device.address, self.disconnect_callback)
				await self.client.connect()
				if not self.client.is_connected:
					self.logger.error("Failed to connect after client creation")
					return
				try:
					paired = await self.client.pair()	# Not necessary: protection_level=1
					self.logger.info(f"Paired: {paired}")
				except NotImplementedError as e:
					# The UI necessary to connect should be a window that reads:
					#
					# Connection Request from: Mario XXXX_x_x
					# To connect to the device, click Connect to complete the connection process.
					#
					# To reject the connection with the device, click Cancel.
					# [ ] Ignore this device     [Cancel] [Connect]
					self.logger.info(f"MacOS pairing skipped, either already paired or hoping subsequent GATT writes will force UI to pop up...")

				self.logger.info("Connected to "+self.shortname+"! ("+str(device.name)+")")
				self.connected = True
				self.address = device.address

				# FIXME: WeDo needs you to sub to all these different chars for data
				await self.client.start_notify(self.btle_uuid_sensor, self._device_events)
				await self.client.start_notify(self.btle_uuid_values, self._device_events)
				await self.client.start_notify(self.hub_attached_io_, self._device_events)

				# LWP Devices attach all their LPF Devices via bt messages when you connect to them
				# WeDo2... does not
				# Is that true, though?  Maybe you need to be attached to attached_io_ UUID

				# So, enumerate them all by inspecting their UUIDs ...
				# (see dump_status())
				#
				# ... and match them to WeDo_Device.py devices
				#	TODO: emulate _init_port_data()
				#
				# Then, _set_hardware_subscription() below should "just work"... right?

				# turn back on everything everybody registered for (For reconnection)
				for event_sub_type,sub_count in self.BLE_event_subscriptions.items():
					if sub_count > 0:
						if not self._set_hardware_subscription(event_sub_type, True):
							self.logger.error("INVALID Subscription option on connect:"+event_sub_type)

				self._inital_connect_updates()

				# Signal connect finished
				self.message_queue.put(('info','player',self.shortname))
				# Replace the above signal with something more accurate
				self.message_queue.put(('info','connected',self.shortname))

			except Exception as e:
				self.logger.error("Unable to connect to "+str(device.address) + ": "+str(e))

		# Won't drain that info,player message without this
		await self._drain_messages()
		self.watchdogs['device_init'] = datetime.datetime.now()

	# Overrideable
	def _inital_connect_updates(self):
		#print("Advertisement:")
		#print(self.advertisement)
		#print("Status...")
		#self.dump_status()
		pass

# TODO: Alright, how to hook completely different payloads into existing device classes...
#		payload = bytearray([	0x01,	# Port 1 or 2
#								0x01,	# Command: motor speed (1)
#								0x01,	# Length of following arguments (1)
#								100])	# speed (1-100 negative for reverse 255-156 zero to stop)
#		self._gatt_send(payload)
#		await asyncio.sleep(2)
#		payload = bytearray([	0x01,	# Port 1 or 2
#								0x01,	# Command: motor speed (1)
#								0x01,	# Length of following arguments (1)
#								0])	# speed (1-100 negative for reverse 255-156 zero to stop)
#		self._gatt_send(payload)
#
# Maybe DI the Writer with a payload object that's protocol conformant (.getLWPPayload, .getWeDoPayload)
# to write whatever the Writer knows to write

	# Checks all Properties and Ports for LPF devices that handle the given message_type
	# Subscribes or unsubscribes to these messages as requested
	def _set_hardware_subscription(self, message_type, should_subscribe=True):

		if not message_type in self.BLE_event_subscriptions:
			self.logger.debug(f'No known devices generate {message_type}')
			return False

#		for port in self.ports:
#		# what if... we used the UUIDs for the ports

#			await self.ports[port].subscribe_to_messages(message_type, should_subscribe, self.gatt_writer)
#			# and then attached WeDo_Device.py subclasses to it
		return True

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
			attaching_device.hw_ver_str = ''	# FIXME: Possible this data is in the connection data
			attaching_device.fw_ver_str = ''
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

	# Returns false if unprocessed
	# Override in subclass, call super if you don't process the bluetooth message type
	async def _process_bt_message(self, bt_message):
		msg_prefix = self.shortname+" "

		if 'type' in bt_message:
			if Decoder.message_type_str[bt_message['type']] == 'hub_attached_io':
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

					if bt_message['io_type_id'] == LDev.MATRIX:
						# Auto-detaches the Matrix, but of course old hubs do...
						print(f"ERROR: This hub will NOT operate {dev} properly!")

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
					self.logger.debug(f"{msg_prefix} Attached IO RAW: {' '.join(hex(n) for n in bt_message['raw'])} len:{len(bt_message['raw'])} sender:{bt_message['char_uuid']}")


	# 		if bt_message['char_uuid'].lower() == self.hub_attached_io_.lower():
	# 			if len(bt_message['raw']) == 12:
	# 				if bt_message['raw'][3] in Decoder.io_type_id_str:
	# 					self._init_port_data(bt_message)
	# 					print(f"Attached Device {Decoder.io_type_id_str[bt_message['raw'][3]]} on port {bt_message['raw'][0]}")
	# 				else:
	# 					print(f"Attached unknown Device {bt_message['raw'][3]}")
	# 			elif len(bt_message['raw']) == 2:
	# 				if bt_message['raw'][1] == 0:
	# 					print(f"Device Detached from Port {bt_message['raw'][0]}")
	# 				else:
	# 					print(f"Attached unknown Device {bt_message['raw'][3]}")
	# 			else:
	# 				self.logger.debug(f"{msg_prefix} Attached IO RAW: {' '.join(hex(n) for n in bt_message['raw'])} len:{len(bt_message['raw'])} sender:{bt_message['char_uuid']}")

			# FIXME: May not be the exactly correct signal
			elif Decoder.message_type_str[bt_message['type']] == 'port_mode_info':
				# FIXME:
				print(msg_prefix+bt_message['readable'])

		elif bt_message['char_uuid'].lower() == self.btle_uuid_sensor.lower():

			# FIXME: Devices respond using pretty much what you would expect, so delegate this properly to them

			if len(bt_message['raw']) >= 2 and bt_message['raw'][0] == 0x2:
				sensor_port = bt_message['raw'][1]
				self.logger.debug(f"{msg_prefix} Sensor Data on port {sensor_port} RAW: {' '.join(hex(n) for n in bt_message['raw'][2:])} len:{len(bt_message['raw'][2:])}")
				# WeDo2  Sensor Data on port 6 RAW: 0x3 len:1
				#		Port 6 is RGB and 0x3 is blue
				#		It gets this data before all the ports are initialized, sooo, eh
			else:
				self.logger.debug(f"{msg_prefix} Unknown Sensor data: RAW: {' '.join(hex(n) for n in bt_message['raw'])} len:{len(bt_message['raw'])} sender:{bt_message['char_uuid']}")
		else:
			self.logger.debug(f"{msg_prefix} RAW: {' '.join(hex(n) for n in bt_message['raw'])} len:{len(bt_message['raw'])} sender:{bt_message['char_uuid']}")


		if bt_message['error']:
			return False
		else:
			return True

	def interrogate_ports(self):
		print("Don't know how to interrogate yet")
		self.dump_status()

	# Send any attached devices a message to process (or a specific device on a port)
	def send_device_message(self, devtype, message, port=None):

#		payload = bytearray([0x5, 0x2, 0x4, 0xB8, 0x01, 0xE8, 0x03])
			# 0x5 Port 5 (piezo)
			# 0x2 Command (play)
			#04B801E803

		if message[0] == '__internal':
			print("Hacky...")
			# A subscribe to notifications of port command
			payload = bytearray([
				0x1,
				0x2,
				0x1,
				34,
				0x1,
				0x1,0x0,0x0,0x0,
				0x0,
				0x1
			])
			self._gatt_send(payload)
		else:
			print(f"FIXME: Not sending {message}")

				# Write stuff here to configure devices?
				# 0x1	Command ID (SDK name) (0: input value, 1: input format) (SDK never writes to command input value)
				# 0x2	Command Type (SDK name) (0: clear, 1: read, 2: write)
				# 0x1	Port Number (SDK name: Connect ID)
				# --- end LEInputCommand prefix and begin payload
				#22	Port ID (22 or Tilt sensor, 0x17: RGB built-in)
				#01	Absolute mode (0x0 indexed)
				#0x1 0x0 0x0 0x0	delta (value here: 1)
				#02 (SI format)
				#01 Notification Enable (0x0 disable)


		pass

# Device Writes
# Header
# 0: port (connectID in SDK)
# 1: "commandID"
#	0x01: Motor Power
#	0x02: Play Piezo
#	0x03: Stop Piezo
#	0x04: Set RGB
#	0x05: Direct Write
# 2: payload_size.  Length of subsequent bytes

# LED Payload (3)
# 3: Red
# 4: Green
# 5: Blue

# LED Payload (1) (Indexed)
# 3: Color Index

# Piezo Payload (4):
# 3-4: frequency (16-bit)
# 5-6: milliseconds (16-bit)

# Stop Piezo (0)

# Motor speed (1)
# 3: Motor speed, signed

# Direct Writes
#	Reset Any Sensor Payload (3) (specify via port in header?)
#		3: 0x44
#		4: 0x11
#		5: 0xAA
