import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
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

			# One is roll (LED forward, roll clockwise is positive
			# Two is pitch (positive is LED forward, clockwise)
			# Three is yaw (spin flat on table, negative is clockwise spin)

			# Does not zero, you'll have to figure that out yourself
			# FIXME: Or I could do a zero-ing function

			# The measurement is in "DPS" which is degrees per second but these
			# numbers are so twitchy they might be some fraction of a degree

			return ('imu', 'rotational', (one, two, three) )
		else:
			print('UNKNOWN IMU ROTATIONAL GYRO DATA '+' '.join(hex(n) for n in data))
			return None



