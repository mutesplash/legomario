import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class BoostUselessTurtle(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x42
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.delta_interval = 0

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'TRIGGER', ()],	# NO IO: Despite this, returns zeroes
																# Sending 0xC8 via WriteDirectModeData once powered the device off!
																# Sending 0xFF will hard lock the device and you will have to drop the battery
			1: [ self.delta_interval, False, 'CANVAS', ()],	# NO IO: Also single value of zero
															# You can send it 0x0 - 0x6 and it will just return that number
															# Greater than 0x6 will throw a lego protocol generic_error (0x5) 'Invalid use of command' (0x6)
															# Becomes angry if you send more then 13 bytes after the mode and will not return the first byte you set
			2: [ self.delta_interval, False, 'VAR', ()]		# NO IO: Oooh, different!  FOUR zeroes!
															# Can send this the max payload size of 256 and nothing happens
		}
