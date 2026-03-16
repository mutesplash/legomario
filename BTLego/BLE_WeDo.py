import asyncio
import uuid
import logging
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .Decoder import Decoder

from .BLE_Device import BLE_Device

class BLE_WeDo(BLE_Device):

	# If there was a level five... unfortunately, too complicated to bother implementing
	TRACE = True

	# ---- Initializations, obviously ----

	def __init__(self, advertisement_data=None):
		super().__init__(advertisement_data)

		# WeDo2
		# Thanks pybricks
		# https://github.com/pybricks/technical-info/blob/master/assigned-numbers.md
		#hub_service = '00001523-1212-efde-1523-785feabcd123'
		#name_characteristic = '00001524-1212-efde-1523-785feabcd123'	R/W
		#button_state_ = '00001526-1212-efde-1523-785feabcd123'			R/N
		#attached_io_ '00001527-1212-efde-1523-785feabcd123'
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
		#self.characteristic_uuid = '00001560-1212-EFDE-1523-785FEABCD123'	# Sensor Value, input
		#self.characteristic_uuid = '00001561-1212-EFDE-1523-785FEABCD123'	# Value Format, input
		#self.characteristic_uuid = '00001563-1212-EFDE-1523-785FEABCD123'	# Input command

		# Other people report using handle 0x3d (61)
		# But my hub didn't have 61, it had 60, which was identified by this UUID
		# Moral of the story, don't use handles, always UUIDs?

		self.characteristic_uuid = '00001565-1212-efde-1523-785feabcd123'	# Output command

		self.packet_decoder = Decoder.decode_wedo2_packet

	async def connect(self, device):
		async with self.lock:
			self.logger.info("Connecting to "+str(self.system_type)+"...")
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

				self.logger.info("Connected to "+self.system_type+"! ("+str(device.name)+")")
				self.connected = True
				self.address = device.address

				# FIXME: WeDo needs you to sub to all these different chars for data
				# await self.client.start_notify(self.characteristic_uuid, self._device_events)

				# LWP Devices attach all their LPF Devices via bt messages when you connect to them
				# WeDo2... does not
				# Is that true, though?  Maybe you need to be attached to attached_io_ UUID

				# So, enumerate them all by inspecting their UUIDs ...
				#for svc in self.client.services:
				#	print(f'Service: {svc}')
				#	for handle_info in svc.characteristics:
				#		print(f"\t Svc. Char.: {handle_info}")
				#
				# ... and match them to WeDo_Device.py devices
				#	TODO: emulate _init_port_data()
				#
				# Then, _set_hardware_subscription() below should "just work"... right?

				# turn back on everything everybody registered for (For reconnection)
				for event_sub_type,sub_count in self.BLE_event_subscriptions.items():
					if sub_count > 0:
						if not await self._set_hardware_subscription(event_sub_type, True):
							self.logger.error("INVALID Subscription option on connect:"+event_sub_type)

				await self._inital_connect_updates()

				# Signal connect finished
				self.message_queue.put(('info','player',self.system_type))
				# Replace the above signal with something more accurate
				self.message_queue.put(('info','connected',self.system_type))

			except Exception as e:
				self.logger.error("Unable to connect to "+str(device.address) + ": "+str(e))

		# Won't drain that info,player message without this
		await self._drain_messages()

	# Overrideable
	async def _inital_connect_updates(self):
		print("Advertisement:")
		print(self.advertisement)
		print("Status...")
		await self.dump_status()

# TODO: Alright, how to hook completely different payloads into existing device classes...
#		payload = bytearray([	0x01,	# Port 1 or 2
#								0x01,	# Command: motor speed (1)
#								0x01,	# Length of following arguments (1)
#								100])	# speed (1-100 negative for reverse 255-156 zero to stop)
#		await self._gatt_send(payload)
#		await asyncio.sleep(2)
#		payload = bytearray([	0x01,	# Port 1 or 2
#								0x01,	# Command: motor speed (1)
#								0x01,	# Length of following arguments (1)
#								0])	# speed (1-100 negative for reverse 255-156 zero to stop)
#		await self._gatt_send(payload)

	# Checks all Properties and Ports for LPF devices that handle the given message_type
	# Subscribes or unsubscribes to these messages as requested
	async def _set_hardware_subscription(self, message_type, should_subscribe=True):

		if not message_type in self.WeDo2_event_subscriptions:
			self.logger.debug(f'No known devices generate {message_type}')
			return False


#		for port in self.ports:
#		# what if... we used the UUIDs for the ports

#			await self.ports[port].subscribe_to_messages(message_type, should_subscribe, self.gatt_writer)
#			# and then attached WeDo_Device.py subclasses to it
		return True



	# Returns false if unprocessed
	# Override in subclass, call super if you don't process the bluetooth message type
	async def _process_bt_message(self, bt_message):
		msg_prefix = self.system_type+" "

		#self.logger.debug(msg_prefix+" "+bt_message['readable'])
		self.logger.debug(f"{msg_prefix} RAW: {bt_message['raw']}")

		if bt_message['error']:
			return False
		else:
			return True
