import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class PUH_BT_RSSI(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x38
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'RSSI ', ('rssi',)]		# Note the space...
		}

	def decode_pvs(self, port, data):
		# Lower numbers are larger distances from the computer
		rssi8 = int.from_bytes(data, byteorder="little", signed=True)
		return ('rssi', 'controller_rssi', rssi8 )
