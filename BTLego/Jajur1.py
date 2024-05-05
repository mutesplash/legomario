import asyncio
from queue import SimpleQueue
from collections.abc import Iterable

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder, LDev

# Boost Hub, Bricklink calls this No 1 but I don't see that anywhere else
class Jajur1(BLE_Device):

	def __init__(self,advertisement_data=None, json_code_dict=None):
		super().__init__(advertisement_data)

		self.mode_probe_ignored_info_types = ( 0x7, 0x8 )	# Doesn't support motor bias or capability bits
		# FIXME: HOWEVER, I haven't attached a really, really dumb LPF2 motor to it: ie 0x1 or something, so MAYBE

	# Override
	async def _process_bt_message(self, bt_message):

		if Decoder.message_type_str[bt_message['type']] == 'hub_attached_io':
			event = Decoder.io_event_type_str[bt_message['event']]

			if event == 'attached':
				devid = bt_message['io_type_id']
				if (
					# BUT, it will read selected mode data from it like speed, pos, apos
					devid == LDev.CONTROLPLUS_LARGE
					or devid == LDev.MOTOR_S
					or devid == LDev.MOTOR_M_G
					or devid == LDev.MOTOR_M_B
					or devid == LDev.MOTOR_L_G
					or devid == LDev.MOTOR_L_B
					):

					print(f"WARNING: This hub will NOT power {Decoder.io_type_id_str[devid]}")
				elif devid == LDev.MATRIX:
					# It constantly reconnects to it.  Similar to how BuildHAT
					# used to work when you didn't specify full power to the
					# port.
					# https://philohome.com/motors/motorcomp.htm
					# That would explain why the above motors won't work either,
					# since they seem to use more wattage than the MOTOR_BOOST
					# that works fine
					print(f"ERROR: This hub will NOT operate {Decoder.io_type_id_str[devid]} properly!")

		return await super()._process_bt_message(bt_message)
