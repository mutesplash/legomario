import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from .LPF_EncoderMotor import LPF_EncoderMotor

class LPF_TachoMotor(LPF_EncoderMotor):

	def __init__(self, port=-1):
		super().__init__(port)

		self.mode_subs[3] = [ self.delta_interval, False, 'APOS', ('motor_apos',)]

	def decode_pvs(self, port, data):
		# FIXME: You're gonna want to set the deltas for POS and APOS...

		# Mode 3
		if len(data) == 2:
			# -180 to 179
			apos = int.from_bytes(data[0:2], byteorder="little", signed=True)
			return ('motor_apos','apos',apos )

		return super().decode_pvs(port, data)

	async def send_message(self, message, gatt_payload_writer):
		'''
		Message tuple:
		( 'set_position', angle )
			Where angle is an integer from -180 to 179

		'''
		processed = await super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]
		payload = None
		mode = -1

		if action == 'set_position':
			mode = 0x3
			angle = int(parameters[0])

			if angle > 179:
				angle = 179
			if angle < -180:
				angle = -180

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode	# Mode 3 "Absolute Position"
			])
			payload += bytearray(angle.to_bytes(length=2, byteorder='little', signed=True))
			payload[0] = len(payload)

		if payload:
			await gatt_payload_writer(payload)
			return True
		return False
