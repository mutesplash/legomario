import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class RGB(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x17
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# Why, again?
		self.delta_interval = 1

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'COL O', ()],		# Color mode: 0 - 0xA, DIS for Discrete
			1: [ self.delta_interval, False, 'RGB O', ()]		# RGB Mode: r,g,b (0-255 each), ABS for absolute color values
		}

	async def send_message(self, message, gatt_payload_writer):
		"""
		Message tuple:
		( 'set_color', color_number)
			Where color_number is an integer from BTLego.Decoder.rgb_light_colors

			Writes to mode 0, listed as COL O in the probe, presumably standing for Color Output
			Typically has no symbol, except the handset lists this as idx, presumably for Index
		( 'set_rgb', (red, green, blue))
			Where each color is an integer 0 to 255 for the LED's intensity

			Mode 1 write, RGB O for RGB Output
			Handset lets us know the symbol is rgb

		The handset uses a zero instead of the capital O in the name as an oddity.

		The modes are not supposed to be readable according to the port mode information,
		and when read, return seemingly useless data.  FIXME: RECHECK THIS
		"""

		processed = await super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]
		payload = None
		mode = -1

		if action == 'set_color':
			mode = 0x0
			color = int(parameters[0])

			if color not in Decoder.rgb_light_colors:
				return

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Mode 0 "COL O"
				color
			])
			payload[0] = len(payload)

		elif action == 'set_rgb':
			mode = 0x1
			red, green, blue = parameters
			def nomalize_color(c):
				if c > 255:
					c = 255
				if c < 0:
					c = 0
				return int(c)
			red = nomalize_color(red)
			green = nomalize_color(green)
			blue = nomalize_color(blue)

			payload = bytearray([
				0x10,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
						# Node poweredup uses 0x11 here always
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Mode 1 "RGB O"
				red,
				green,
				blue
			])
			payload[0] = len(payload)

		if payload:
			await self.select_mode_if_not_selected(mode, gatt_payload_writer)
			await gatt_payload_writer(payload)
			return True
		return False
