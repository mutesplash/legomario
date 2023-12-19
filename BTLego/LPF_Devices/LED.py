import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class LED(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.LPF

		self.port = port

		self.port_id = 0x8
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			# FIXME: Not probed
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def send_message(self, message):
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]
		ret_message = None

		if action == 'power':
			power = int(parameters[0])

			if power > 100:
				power = 100
			if power < 0:
				power = 0

			mode = 0	# Passive device, no mode... right?

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
			return { 'gatt_send': (payload,) }

		return None