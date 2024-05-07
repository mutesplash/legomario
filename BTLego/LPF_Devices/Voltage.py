import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Voltage(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x14
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'VLT L', ('voltage',)],
			1: [ self.delta_interval, False, 'VLT S', ()]
		}

	def decode_pvs(self, port, data):
		# FIXME: L or S and what do they mean?
		# '3362' on VLT L when the multimeter volts are 7.90
		volts16 = int.from_bytes(data, byteorder="little", signed=False)
		return ('voltage', 'millivolts', volts16 )
