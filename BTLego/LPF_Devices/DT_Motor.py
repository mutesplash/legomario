import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class DT_Motor(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x29
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'ONSEC', ()],
			1: [ self.delta_interval, False, 'T MOT', ()]
		}

	async def send_message(self, message, gatt_payload_writer):
		# ( action, (parameters,) )
		action = message[0]
		parameters = message[1]

		if action == 'set_speed':
			# This seems like a "go until I detect out-of-range resistance (zero or too much)" mode
			speed = parameters[0]

			payload = self.motor_speed_payload_for_gatt_write(speed)
			if payload:
				await gatt_payload_writer(payload)
				return True

		return False

	def motor_speed_payload_for_gatt_write(self, speed):
		# -100 to 100

		requested_speed = int(speed)
		if requested_speed > 100 or requested_speed < -100:
			return None

		converted_speed = DT_Motor.set_percent_speed_range_to_port_int(requested_speed)

		motor_mode = 0
		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x81,	# Command: port_output_command
			# end header
			self.port,
			0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
					# Node poweredup and legoino use 0x11 here always
			0x51,	# Subcommand: WriteDirectModeData
			motor_mode,	# I _THINK_ this is the mode
			converted_speed
		])
		payload[0] = len(payload)

		return payload

	def set_percent_speed_range_to_port_int(speed):

		# This doesn't make a lot of sense to me, but the speed is
		# 0-100 forwards (lead with light) and 156-255 backwards

		if speed > 100:
			return 100

		if speed >= 0:
			return speed

		if speed < -100:
			return 156

		return 256 + speed

#'duplotrain_motor'