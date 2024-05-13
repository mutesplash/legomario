import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class PUH_IMU_Gyro(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x3a
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.delta_interval = 5

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'ROT', ('puh_rotational_acc',)],
		}

		self.zero_values = None
		self.next_value_zero = False

	def _relative_to_zero_values(self, one, two, three):
		(r1, r2, r3) = (one, two, three)
		if self.zero_values:
			if self.zero_values[0] != 0:
				r1 = one - self.zero_values[0]
			if self.zero_values[1] != 0:
				r2 = two - self.zero_values[1]
			if self.zero_values[2] != 0:
				r3 = three - self.zero_values[2]

		return ( r1, r2, r3 )

	# Decode Port Value - Single
	# Return (type, key, value)
	def decode_pvs(self, port, data):
		if port != self.port:
			print('Bad port')
			return None

		if len(data) == 6:
			one = int.from_bytes(data[0:2], byteorder="little", signed=True)
			two = int.from_bytes(data[2:4], byteorder="little", signed=True)
			three = int.from_bytes(data[4:], byteorder="little", signed=True)

			if self.next_value_zero:
				self.next_value_zero = False
				self.zero_values = ( one, two, three )

			# One is roll (LED forward, roll clockwise is positive
			# Two is pitch (positive is LED forward, clockwise)
			# Three is yaw (spin flat on table, negative is clockwise spin)

			# Raw values are not zeroed

			# The measurement is in "DPS" which is degrees per second but these
			# numbers are so twitchy they might be some fraction of a degree

			return ('imu', 'rotational', self._relative_to_zero_values(one, two, three) )
		else:
			print('UNKNOWN IMU ROTATIONAL GYRO DATA '+' '.join(hex(n) for n in data))
			return None

	async def send_message(self, message, gatt_payload_writer):
		processed = await super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]

		# Hub should be VERY STILL when it gets this command
		if action == 'set_zero':
			mode = 0x0
			self.next_value_zero = True
			return await self.get_port_info(mode, gatt_payload_writer)
