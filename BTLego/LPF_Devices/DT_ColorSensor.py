import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class DT_ColorSensor(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x2b
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'COLOR', ('duplotrain_color',)],
			1: [ self.delta_interval, False, 'C TAG', ('duplotrain_tag',)],	# Don't really know what this is
			2: [ self.delta_interval, False, 'REFLT', ('duplotrain_reflectivity',)],
			3: [ self.delta_interval, False, 'RGB I', ('duplotrain_rgb',)],
			4: [ self.delta_interval, False, 'CALIB', ()]
		}

	def decode_pvs(self, port, data):
		if port != port:
			return None

		if len(data) == 1:
			color_int = int(data[0])

			if color_int in Decoder.rgb_light_colors:
				# Incredibly unreliable!  Only VAGUELY related to Decoder.rgb_light_colors.  Like, red seems to work?
				return ('duplotrain_color','color',color_int)
			elif color_int > 0xa and color_int < 0x32:
				return ('duplotrain_reflectivity','measurement',color_int)
			elif color_int == 0xff:
				return ('duplotrain_tag','unknown','MAX_INT')
		elif len(data) == 6:
			# IDK why it goes > 255
			r = int.from_bytes(data[:2], byteorder="little")
			g = int.from_bytes(data[2:4], byteorder="little")
			b = int.from_bytes(data[4:6], byteorder="little")
			return ('duplotrain_rgb','triplet',(r,g,b) )

		return None
