import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class BoostTilt(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x28
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.delta_interval = 1

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'ANGLE', ('boost_rollpitch',)],	# IN DEG
			1: [ self.delta_interval, False, 'TILT', ('boost_tilt',)],	# IN DIR
			2: [ self.delta_interval, False, 'ORINT', ('boost_orientation',)],	# IN DIR
			3: [ self.delta_interval, False, 'IMPCT', ('boost_impact',)],	# IN IMP
			4: [ self.delta_interval, False, 'ACCEL', ('boost_accel',)],	# IN ACC
			5: [ self.delta_interval, False, 'OR_CF', ()],	# IN SID
			6: [ self.delta_interval, False, 'IM_CF', ()],	# IN SEN
			7: [ self.delta_interval, False, 'CALIB', ()],	# IN CAL
		}

	def decode_pvs(self, port, data):
		if port != self.port:
			print('Bad port')
			return None

		if len(data) == 0:
			print('No data')
			return None

		def unsigned_to_signed(lpf_uint8):
			sign = lpf_uint8 >> 7
			absolute = lpf_uint8 ^ 128
			if sign:
				return -absolute
			return lpf_uint8

		# ANGLE
		if self.mode_subs[0][1]:
			if len(data) != 2:
				print(f'WRONG DATA LEN FOR MODE 0: {len(data)}')
				return None

			lr = data[0]
			ud = data[1]

			if lr > 127:
				lr = -(256-data[0])
			if ud > 127:
				ud = -(256-data[1])

			# Ok, positive is roll left 0 to 90, but roll right is is 255 to 166)
			# so we'll have to translate (and the right side is missing a degree?)
			# This makes sense in a weird circle that is measured in degrees,
			# but only can enumerate 255 degrees, but since it doesn't measure
			# half the circle, it just puts the innumerable degrees in that part

			# Roll Right: -1 to -90
			# Roll Left: 1 to 90
			# Pitch up: -1 to 90
			# Pitch down: 1 to 90
			# Neutral position: 0
			return ( 'boost', 'rollpitch', (lr,ud) )

		# TILT:
		elif self.mode_subs[1][1]:
			if len(data) != 1:
				print(f'WRONG DATA LEN FOR MODE 1: {len(data)}')
				return None

			# Does not detect yaw
			if data[0] == 0x0:
				return ( 'boost', 'tilt', 'neutral' )
			elif data[0] == 0x3:
				return ( 'boost', 'tilt', 'down' )	# pitch
			elif data[0] == 0x5:
				return ( 'boost', 'tilt', 'right' )	# roll
			elif data[0] == 0x7:
				return ( 'boost', 'tilt', 'left' )	# roll
			elif data[0] == 0x9:
				return ( 'boost', 'tilt', 'up' )	# pitch
			else:
				print(f'UNKNOWN TILT TYPE {data[0]}')

		# ORINT	six sided cube 0-5
		elif self.mode_subs[2][1]:
			if len(data) != 1:
				print(f'WRONG DATA LEN FOR MODE 2: {len(data)}')
				return None

			if data[0] == 0x0:
				return ('boost','orientation','faceup')
			elif data[0] == 0x1:
				return ('boost','orientation','point up')
			elif data[0] == 0x2:
				return ('boost','orientation','point down')
			elif data[0] == 0x3:
				return ('boost','orientation','B-side up')	# Left
			elif data[0] == 0x4:
				return ('boost','orientation','A-side up')	# Right
			elif data[0] == 0x5:
				return ('boost','orientation','upside-down')
			else:
				print(f'UNKNOWN ORIENTATION TYPE {data[0]}')

		# IMPCT bump sensor
		elif self.mode_subs[3][1]:
			if len(data) != 4:
				print(f'WRONG DATA LEN FOR MODE 3: {len(data)}')
				return None

			crash_count = int.from_bytes(data, byteorder="little", signed=False)
			return ('boost', 'impacts', crash_count)

		# ACCEL constant stream
		elif self.mode_subs[4][1]:
			if len(data) != 3:
				print(f'WRONG DATA LEN FOR MODE 4: {len(data)}')
				return None

			# The numbers reported here are in units of half-foot per second squared
			# (Which, makes no sense at all, but let me finish)
			# meaning at rest an absolute result of '64' down would be
			# (6*64=384 inches) or 32 ft/sec^2, which is the gravitational
			# acceleration on earth which DOES make sense so divide all numbers
			# from this by 2 to get ft/s^2

			right_accel = unsigned_to_signed(data[0])		# Positive Accel with A as leading side
			forward_accel = unsigned_to_signed(data[1])		# Positive Accel with LED side leading
			downward_accel = unsigned_to_signed(data[2])	# Positive Accel with bottom side leading

			# X, Y, Z if the LED is pointed 'up' on a sheet of graph paper. Positive Z is through the paper
			return ('boost', 'accel', ( right_accel, forward_accel, downward_accel))

		# OR_CF constantly zero, dunno...
		# IM_CF constant number




