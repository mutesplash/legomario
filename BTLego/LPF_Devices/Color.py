import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Color(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		self.port_id = 0x3d
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'COLOR', ()],
			1: [ self.delta_interval, False, 'REFLT', ()],
			2: [ self.delta_interval, False, 'AMBI', ()],
			3: [ self.delta_interval, False, 'LIGHT', ()],
			4: [ self.delta_interval, False, 'RREFL', ()],
			5: [ self.delta_interval, False, 'RGB I', ('rgb_i',)],
			6: [ self.delta_interval, False, 'HSV', ()],
			7: [ self.delta_interval, False, 'SHSV', ()],
			8: [ self.delta_interval, False, 'DEBUG', ()]
		}

	def decode_pvs(self, port, data):
		if port != self.port:
			return None

		if len(data) == 8:
			# IDK why it goes > 255
			r = int.from_bytes(data[:2], byteorder="little")
			g = int.from_bytes(data[2:4], byteorder="little")
			b = int.from_bytes(data[4:6], byteorder="little")
			i = int.from_bytes(data[6:8], byteorder="little")
			return ('rgb_i','quad',(r, g, i, i))
		return None
