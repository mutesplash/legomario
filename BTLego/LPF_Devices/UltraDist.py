import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class UltraDist(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		self.port_id = 0x3e
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'DISTL', ()],
			1: [ self.delta_interval, False, 'DISTS', ()],
			2: [ self.delta_interval, False, 'SINGL', ()],
			3: [ self.delta_interval, False, 'LISTN', ()],
			4: [ self.delta_interval, False, 'TRAW', ()],
			5: [ self.delta_interval, False, 'LIGHT', ()],
			6: [ self.delta_interval, False, 'PING', ()],
			7: [ self.delta_interval, False, 'ADRAW', ()]
			8: [ -1, False, 'CALIB', ()]	# NO IO
		}

	async def send_message(self, message, gatt_payload_writer):
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]

		if action == 'leds':
			# Relative to a theoretical robot: ie: right would be their right eye
			right_upper, left_upper, right_lower, left_lower = parameters

			def rangecheck(led_power):
				if led_power > 100:
					led_power = 100
				if led_power < 0:
					led_power = 0
				return led_power

			right_upper = int(rangecheck(right_upper))
			left_upper = int(rangecheck(left_upper))
			right_lower = int(rangecheck(right_lower))
			left_lower = int(rangecheck(left_lower))

			mode = 5

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Appendix 6.1
				right_upper,
				left_upper,
				right_lower,
				left_lower
			])
			payload[0] = len(payload)
			await gatt_payload_writer(payload)
			return True

		return False
