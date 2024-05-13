import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class PUH_IMU_Temp(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x3C
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.delta_interval = 5

		# Experiments with ice packs lead me to believe that
		# the sensor on port 96 is the external temperature
		# while the sensor on port 61 is probably the cpu, which will
		# produce some wild 20-degree variances within a second

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'TEMP', ('temp',)]
		}


	# Decode Port Value - Single
	# Return (type, key, value)
	def decode_pvs(self, port, data):
		if port != self.port:
			print('Bad port')
			return None

		if len(data) != 2:
			print('UNKNOWN TEMPERATURE DATA '+' '.join(hex(n) for n in data))
			return None

		# Looks like deci-celsius.  Divide by 10
		temp = int.from_bytes(data, byteorder="little", signed=True)

		return ('temp',port,temp)
