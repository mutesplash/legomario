import asyncio

from .BLE_LWP_Device import BLE_LWP_Device
from .Decoder import Decoder

class DuploTrain(BLE_LWP_Device):

	def __init__(self, advertisement_data=None, shortname=''):
		super().__init__(advertisement_data, shortname)

		self.part_identifier = "28743c01"

		self.minimum_attached_ports = 6

		self.mode_probe_ignored_info_types = ( 0x7, 0x8 )	# Doesn't support motor bias or capability bits

	# "ONSEC"
	# stalls it out
	# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)
	# These ancient scribblings in the array refer to the device type, the port it's on, the delta interval, and if you should subscribe
	#await self._set_port_subscriptions([[self.device_ports[Decoder.io_type_id['DT MOTOR']], 1,1,0 ]])
	# Lets it go (but not to the "current" speed)
	#await self._set_port_subscriptions([[self.device_ports[Decoder.io_type_id['DT MOTOR']], 0,1,0 ]])

#		await asyncio.sleep(0.42)	# Maximum wait if the thing only accepts motor speeds in pulses or whatever is happening there
#		await self.write_mode_motor_speed(50)

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
			target_dev.send_message( ('play_sound', (0x3,)), self.gatt_writer)
			await asyncio.sleep(1.1)
			target_dev.send_message( ('play_sound', (0x7,)), self.gatt_writer)
			await asyncio.sleep(1.2)
			target_dev.send_message( ('play_sound', (0x7,)), self.gatt_writer)
			await asyncio.sleep(1.2)
			target_dev.send_message( ('play_sound', (0x7,)), self.gatt_writer)
			await asyncio.sleep(1.2)
			target_dev.send_message( ('play_sound', (0x7,)), self.gatt_writer)

	async def pretend_default_green_tile(self):
		# Only sending this to ONE beeper dev.  SEEMS REASONABLE
		target_devs = None
		for attached_port in self.ports:
			dev = self.ports[attached_port]
			if dev.status != 0x0:		# Decoder.io_event_type_str[0x0]
				if dev.port_id == Decoder.io_type_id_ints['DUPLO Train hub built-in beeper']:
					target_dev = dev

		if target_dev:
			target_dev.send_message( ('play_sound', (0x3,)), self.gatt_writer)
			await asyncio.sleep(1)
			target_dev.send_message( ('play_sound', (0xa,)), self.gatt_writer)



