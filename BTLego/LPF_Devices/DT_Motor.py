import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class DT_Motor(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.FIXED

		self.port = port

		self.port_id = 0x29
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 5, False),		# ONSEC
			1: ( 5, False)		# T MOT		IDK what this mode does
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def send_message(self, message):
		# ( action, (parameters,) )
		action = message[0]
		parameters = message[1]

		if action == 'set_speed':
			# This seems like a "go until I detect resistance" mode
			speed = parameters[0]

			payload = self.motor_speed_payload_for_gatt_write(speed)
			if payload:
				return { 'gatt_send': (payload,) }

		return None

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