import asyncio

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder

class DuploTrain(BLE_Device):
	# 0:	Don't debug
	# 1:	Print weird stuff
	# 2:	Print most of the information flow
	# 3:	Print stuff even you the debugger probably don't need
	DEBUG = 0

	def __init__(self, advertisement_data=None):
		super().__init__(advertisement_data)

		# This thing is cranky and slow.  It takes 50 seconds to fully probe the thing
		self.gatt_send_rate_limit = 0.2
		self.mode_probe_rate_limit = 1.1

		self.mode_probe_ignored_info_types = ( 0x7, 0x8 )	# Doesn't support motor bias or capability bits

	async def _demo_range_test(self):

		print("Testing...")

		# "ONSEC"
		# stalls it out
		#await self._set_port_subscriptions([[self.device_ports[Decoder.io_type_id['DT MOTOR']], 1,1,0 ]])
		# Lets it go (but not to the "current" speed)
		#await self._set_port_subscriptions([[self.device_ports[Decoder.io_type_id['DT MOTOR']], 0,1,0 ]])

#		await self.write_mode_motor_speed(-50)
#		await asyncio.sleep(2)

#		await asyncio.sleep(0.42)	# Maximum wait if the thing only accepts motor speeds in pulses or whatever is happening there
#		await self.write_mode_motor_speed(50)

		pass

	# ---- Make data useful ----

	# ---- Random stuff ----

	def dp(pstr, level=1):
		if DuploTrain.DEBUG:
			if DuploTrain.DEBUG >= level:
				print(pstr)

	# ---- Bluetooth port writes ----

	async def pretend_default_blue_tile(self):

		# Only sending this to ONE beeper dev.  SEEMS REASONABLE
		target_dev = None
		for attached_port in self.ports:
			dev = self.ports[attached_port]
			if dev.status != 0x0:		# Decoder.io_event_type_str[0x0]
				if dev.port_id == Decoder.io_type_id_ints['DUPLO Train hub built-in beeper']:
					target_dev = dev

		if target_dev:
			await self.process_message_result(target_dev.send_message( ('play_sound', (0x3,)) ))
			await asyncio.sleep(1.1)
			await self.process_message_result(target_dev.send_message( ('play_sound', (0x7,)) ))
			await asyncio.sleep(1.2)
			await self.process_message_result(target_dev.send_message( ('play_sound', (0x7,)) ))
			await asyncio.sleep(1.2)
			await self.process_message_result(target_dev.send_message( ('play_sound', (0x7,)) ))
			await asyncio.sleep(1.2)
			await self.process_message_result(target_dev.send_message( ('play_sound', (0x7,)) ))

	async def pretend_default_green_tile(self):
		# Only sending this to ONE beeper dev.  SEEMS REASONABLE
		target_devs = None
		for attached_port in self.ports:
			dev = self.ports[attached_port]
			if dev.status != 0x0:		# Decoder.io_event_type_str[0x0]
				if dev.port_id == Decoder.io_type_id_ints['DUPLO Train hub built-in beeper']:
					target_dev = dev

		if target_dev:
			await self.process_message_result(target_dev.send_message( ('play_sound', (0x3,)) ))
			await asyncio.sleep(1)
			await self.process_message_result(target_dev.send_message( ('play_sound', (0xa,)) ))



