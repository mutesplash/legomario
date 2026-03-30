import asyncio
import uuid
import logging
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .Decoder import Decoder

from .BLE_Device import BLE_Device

class BLE_Smartbrick(BLE_Device):

	# If there was a level five... unfortunately, too complicated to bother implementing
	TRACE = False

	# ---- Initializations, obviously ----

	def __init__(self, advertisement_data=None):
		super().__init__(advertisement_data)

		# WDX
		self.characteristic_uuid = '005F0002-2FF2-4ED5-B045-4C7463617865'
		self.hub_service_uuid = '00001623-1212-efde-1623-785feabcd123'
		self.packet_decoder = Decoder.decode_wdx_packet

	# Overrideable
	async def _inital_connect_updates(self):
		#print(self.advertisement)
		print("Status...")
		self.dump_status()
		print("Interrogating all known WDX Registers...")
		await self.interrogate_known_registers()

	# Returns false if unprocessed
	# Override in subclass, call super if you don't process the bluetooth message type
	async def _process_bt_message(self, bt_message):
		msg_prefix = self.system_type+" "

		self.logger.debug(msg_prefix+" "+bt_message['readable'])

		if bt_message['error']:
			return False
		else:
			return True

	async def interrogate_known_registers(self):
		for x in Decoder.wdx_registers:
			if 'R' in Decoder.wdx_registers[x][1]:
				await self._gatt_send_wdx_read(x)
			else:
				pass
				#self.logger.debug(f'Not interrogating un-readable register {Decoder.wdx_registers[x][0]}')

	# Only worth doing after a firmware update I guess
	async def interrogate_all_registers(self):
		for x in range(0,256):
			await self._gatt_send_wdx_read(x)

	async def _gatt_send_wdx_read(self, register):
		if register > 255 or register < 0:
			return
		payload = bytearray([
			0x1,		# read
			register
		])
		await self._gatt_send(payload)

