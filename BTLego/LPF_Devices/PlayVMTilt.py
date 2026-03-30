import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class PlayVMTilt(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x5d
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'ORINT', ('playvm_tilt',)],
		}

	def decode_pvs(self, port, data):

		# Mode 0
		# "symbol": "QUA",
		if len(data) == 8:
			# -1000 to 1000
			one = int.from_bytes(data[0:2], byteorder="little", signed=True)
			two = int.from_bytes(data[2:4], byteorder="little", signed=True)
			three = int.from_bytes(data[4:6], byteorder="little", signed=True)
			four = int.from_bytes(data[6:8], byteorder="little", signed=True)
			# FIXME: quad being a temporary name, don't know what these numbers are
			return ('playvm_tilt','quad', (one, two, three, four) )

			# Numbers do not wrap, they just go back down (weird)
			# Moving the Hub in a geometric translation does mostly nothing
			# 1 is roll
			# 2 & 3 go up and down opposite of each other during flat spins (yaw)
			# 4 is pitch

		return super().decode_pvs(port, data)
