import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Motion(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.part_identifier = 45304

		self.devtype = Devtype.LPF

		self.delta_interval = 1

		self.port_id = 0x23
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'LPF2-DETECT', ('motion_detect',)],
			1: [ self.delta_interval, False, 'LPF2-COUNT', ('motion_count',)],
			2: [ self.delta_interval, False, 'LPF2-CAL', ()]
		}

	def decode_pvs(self, port, data):

		# Mode 0: Very short-range motion/distance. About a ten stud distance
		# also incredibly imprecise
		if len(data) == 1:
			stud_distance = int.from_bytes(data, byteorder="little", signed=True)
			return ('motion_detect','studs', stud_distance )

		# Mode 1: Count movement
		elif len(data) == 4:
			# Port info is a liar,  Count goes to four figures: 1000
			motion_count = int.from_bytes(data[0:4], byteorder="little")
			return ('motion_count','count', motion_count )

		return super().decode_pvs(port, data)
