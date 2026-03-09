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
		self.characteristic_uuid = '00001560-1212-EFDE-1523-785FEABCD123'	# Sensor Value
		self.characteristic_uuid = '00001561-1212-EFDE-1523-785FEABCD123'	# Value Format
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
