import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class RGB(LPF_Device):

	LED_MODE_RGB = 1
	LED_MODE_COLOR = 0

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x17
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# Why, again?
		self.delta_interval = 1

		self.current_led_mode = -1

		# FIXME: Don't use current_led_mode, use this!
		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'COL O', ()],	# Color mode: 0 - 0xA
			1: [ self.delta_interval, False, 'RGB O', ()]		# RGB Mode: r,g,b (0-255 each)
		}

	# Switch the mode by unsubscribing to the mode you want
	# If a change occurs (and a unsubscribe needs to be sent), return True
	def switch_led_mode(self, action):
		if action == 'set_color':
			if self.current_led_mode != 0:
				self.current_led_mode = 0
				return True
		elif action == 'set_rgb':
			if self.current_led_mode != 1:
				self.current_led_mode = 1
				return True

		return False

	async def send_message(self, message, gatt_payload_writer):
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
			if self.switch_led_mode(action):
				# Hat tip to legoino (Lpf2Hub.cpp) for noting that you have to do the port input format setup
				# to change the input mode instead of just yolo sending it (because that doesn't work)
				# I guess the docs _kind of_ say that but they're not really easy to interpret
				# You _unsubscribe_ to the mode to switch to it
				await self.PIF_single_setup(mode, False, gatt_payload_writer)
			await gatt_payload_writer(payload)
			return True
		return False
