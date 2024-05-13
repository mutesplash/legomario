import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class LPF_BasicMotor(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		# FIXME: Can't subscribe to more than one.  Time to figure out combo modes, right?
		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'POWER', ()],
		}

	def decode_pvs(self, port, data):
		# FIXME: You're gonna want to set the deltas for POS and APOS...

		# Mode 0 or 1
		if len(data) == 1:
			# Negative is face-on counterclockwise
			speed_or_power = int.from_bytes(data[0:2], byteorder="little", signed=True)
			return ('motor_speed','speed',speed_or_power )

		return super().decode_pvs(port, data)

	async def send_message(self, message, gatt_payload_writer):
		'''
		Message tuple:
		( 'set_power', power_value )
			Where power_value is an integer from -100 to 100

			Negative being counterclockwise, except for one of the BoostHubMotor(s)
			so that the same command to both motors drives them in the same direction

			Mode 0 is listed as various names for older or simpler motors,
			but is mostly standardized as POWER

		FIXME: READABLE DESPITE BEING LISTED AS NOT?
		'''
		processed = await super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]
		payload = None
		mode = -1

		if action == 'set_power':
			mode = 0x0
			power = int(parameters[0])

			if power > 100 or power < -100:
				return

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode	# Mode 0 "Power"
			])
			payload += bytearray(power.to_bytes(length=1, byteorder='little', signed=True))
			payload[0] = len(payload)

		if payload:
			# await self.select_mode_if_not_selected(mode, gatt_payload_writer)
			await gatt_payload_writer(payload)
			return True
		return False
