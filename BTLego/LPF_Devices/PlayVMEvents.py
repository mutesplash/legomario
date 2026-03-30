import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class PlayVMEvents(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x5c
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'IDK', ('idk_',)],

			# on Connect
			# PORT 61 LPF_DATA: 0x56 0x0 0x0 0x0 0x0 0x0 0x0 0x0
			# also on Connect, but different
			# PORT 61 LPF_DATA: 0x55 0x0 0x0 0x0 0x0 0x0 0x0 0x0
			# These are not sent on reconnect, usually...

		}
