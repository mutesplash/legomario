import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class PUH_IMU_Position(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x3b
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.delta_interval = 1

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'POS', ('puh_rotational_deg',)],	# Zeroes
			1: [ self.delta_interval, False, 'IMP', ('puh_crashes',)],	# Impact?
			2: [ self.delta_interval, False, 'CFG', ()]
		}

	# Decode Port Value - Single
	# Return (type, key, value)
	def decode_pvs(self, port, data):
		if port != self.port:
			print('Bad port')
			return None

		if self.mode_subs[0][1]:

			if len(data) != 6:
				print('UNKNOWN IMU POSITIONAL DEGREE MODE 0 DATA '+' '.join(hex(n) for n in data))
				return None

			one = int.from_bytes(data[0:2], byteorder="little", signed=True)
			two = int.from_bytes(data[2:4], byteorder="little", signed=True)
			three = int.from_bytes(data[4:], byteorder="little", signed=True)

			# one: Yaw in degrees.  Clockwise 0 to -179.  Counterclockwise 0 to 179.  Zeroed from power-on??
				# Uh, ok, if the brick is pointed with the LED "up" when it's powered on,
				# this will go all the way to 359 if you spin it on the table (starts at 180)
			# two: Pitch.  Positive pointing down.  Pitch down 0 to 90.  Pitch up 0 to -90
			# three: Roll. Roll right 0 to 179.  Roll left 0 to -179

			return ('puh_rotational_deg', 'yaw_pitch_roll', ( one, two, three) )

		elif self.mode_subs[1][1]:
			if len(data) != 4:
				print('UNKNOWN IMU CRASH MODE 1 DATA '+' '.join(hex(n) for n in data))
				return None

			crashes = int.from_bytes(data, byteorder="little", signed=False)

			return ('puh_crashes', 'impact_count', crashes )

		else:
			print('UNKNOWN IMU POSITIONAL DEVICE DATA '+' '.join(hex(n) for n in data))
