import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class LPF_TachoMotor(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		# FIXME: Can't subscribe to more than one.  Time to figure out combo modes, right?
		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'POWER', ()],
			1: [ self.delta_interval, False, 'SPEED', ('motor_speed',)],
			2: [ self.delta_interval, False, 'POS', ('motor_pos',)],
			3: [ self.delta_interval, False, 'APOS', ('motor_apos',)]
		}

	def decode_pvs(self, port, data):
		# FIXME: You're gonna want to set the deltas for POS and APOS...

		# Mode 0 or 1
		if len(data) == 1:
			# Negative is face-on counterclockwise
			speed_or_power = int.from_bytes(data[0:2], byteorder="little", signed=True)
			return ('motor_speed','speed',speed_or_power )

		# Mode 3
		if len(data) == 2:
			# -180 to 179
			apos = int.from_bytes(data[0:2], byteorder="little", signed=True)
			return ('motor_apos','apos',apos )

		# Mode 2
		elif len(data) == 4:
			# 0 to 4294967295 (MAX_INT_32) wraps around
			pos = int.from_bytes(data[0:4], byteorder="little")
			return ('motor_pos','pos',pos )

	async def send_message(self, message, gatt_payload_writer):
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
