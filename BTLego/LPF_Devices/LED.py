import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class LED(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		self.port_id = 0x8
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'LPF2-LIGHT', ()]
		}

	async def send_message(self, message, gatt_payload_writer):
		processed = await super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]

		if action == 'power':
			power = int(parameters[0])

			if power > 100:
				power = 100
			if power < 0:
				power = 0

			mode = 0

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Appendix 6.1
				power
			])
			payload[0] = len(payload)
			await gatt_payload_writer(payload)
			return True

		return False
