import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Tilt(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.part_identifier = 45305

		self.devtype = Devtype.LPF

		self.port_id = 0x22
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# Per the literature:
		# "detect seven different types of orientation:"
		# "Tilt This Way, Tilt That Way, Tilt Up, Tilt Down, No Tilt, Any Tilt, and Shake"
		# https://education.lego.com/v3/assets/blt293eea581807678a/blt87521f32a1f96bff/5f88043c18967612e58a6a00/toolbox-en-us-v1.pdf
		# "Left" is "show the bottom" if the cord is pointed away from you
		# Therefore "right" is "show the top" when cord is pointed away, lego text upside down
		# THEREFORE the correct orientation is cord towards you for L/R to make sense
		# "Tilt down" with the 2x non cord end pointed down is referenced in one of the WeDo2 instructional tutorials

		# Mode 0:
		#	Raw integers.  Use this when you think I have just messed up the data
		#	translation because I wanted negative pitch to be pointing down
		# Mode 1:
		#	Brick in neutral position
		#		negative roll is left, positive is right
		#		negative pitch is down, positive is up
		# Mode 2: (FIXME)
		#	Wire to Left in front of you, same translations
		self.angle_mode = 1

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'LPF2-ANGLE', ('angle',)],
			1: [ self.delta_interval, False, 'LPF2-TILT', ()],
			2: [ self.delta_interval, False, 'LPF2-CRASH', ()],
			3: [ self.delta_interval, False, 'LPF2-CAL', ()]
		}

	def decode_pvs(self, port, data):
		if port != self.port:
			return None

		if len(data) == 2:
			# I'm sure there's some clever way to do this and I'm just... not
			# And now I'm not even using it anymore and I won't delete it
			def unsigned_to_signed(lpf_uint8):
				sign = lpf_uint8 >> 7
				absolute = lpf_uint8 ^ 128
				if sign:
					return -absolute
				return absolute

			# Doesn't detect yaw (brick just spinning on a table, flat)
			roll = data[0]
			pitch = data[1]

			if self.angle_mode == 0:
				return ('angle','raw',(roll, pitch))
			elif self.angle_mode == 1:
				zero_roll = data[0]
				if zero_roll > 127:
					zero_roll = -(255-data[0])

				zero_pitch = data[1]
				if zero_pitch > 127:
					zero_pitch = (255-data[1])
				else:
					zero_pitch = -zero_pitch

				return ('angle','zeroed',(zero_roll, zero_pitch))

		return None
