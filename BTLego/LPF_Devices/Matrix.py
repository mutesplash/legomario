import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Matrix(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		self.port_id = 0x40
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# Why, again?
		self.delta_interval = 1

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ 1, False, 'LEV O', ()],	# Level
			1: [ 1, False, 'COL O', ()],	# Solid Color
			2: [ 1, False, 'PIX O', ()],	# Pixel set
			3: [ 1, False, 'TRANS', ()]		# Set transistion
		}

		self.current_matrix = Matrix.blank_matrix()

	def blank_matrix():
		return [[(0, 0) for x in range(3)] for y in range(3)]

	def validate_pixel(pixel):
		if isinstance(pixel, tuple) and len(pixel) == 2:
			color, brightness = pixel
			if not (isinstance(brightness, int) and isinstance(color, int)):
				return False
			if not (brightness >= 0 and brightness <= 10):
				return False
			if color not in Decoder.rgb_light_colors:
				return False
			return True
		else:
			return False

	def validate_matrix(new_matrix):
		if not isinstance(new_matrix, list):
			return False
		if len(new_matrix) != 3:
			return False
		for x in range(3):
			if len(new_matrix[x]) != 3:
				return False
			for y in range(3):
				if not Matrix.validate_pixel(new_matrix[x][y]):
					return False
		return True

	async def send_message(self, message, gatt_payload_writer):
		processed = await super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]
		payload = None
		mode = -1

		if action == 'set_level':
			mode = 0
			level = int(parameters[0])

			if level < 0 or level > 9:
				return False

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Mode 0: Level
				level
			])
			payload[0] = len(payload)

		elif action == 'set_color':
			mode = 1

			color = int(parameters[0])
			if color not in Decoder.rgb_light_colors:
				return False

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				0x1,	# Mode 1: Color set
				color
			])
			payload[0] = len(payload)

		elif action == 'set_pixels':
			mode = 2

			new_matrix = parameters[0]
			if not Matrix.validate_matrix(new_matrix):
				return False
			else:
				self.current_matrix = new_matrix

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				0x2,	# Mode 2: Pixel set
			])
			for x in range(3):
				for y in range(3):
					# brightness in the upper bits, color in the lower
					payload.append((self.current_matrix[x][y][1] << 4) | self.current_matrix[x][y][0])

			payload[0] = len(payload)

		elif action == 'set_transition':
			mode = 3
			transition_mode = int(parameters[0])

			# Mode 0: No transition, immediate pixel drawing

			# Mode 1: Right-to-left wipe in/out

			# If the timing between writing new matrix pixels is less than one second
			# the transition will clip columns of pixels from the right.

			# Mode 2: Fade-in/Fade-out

			# The fade in and fade out take about 2.2 seconds for full fade effect.
			# Waiting less time between setting new pixels will result in a faster
			# fade which will cause the fade to "pop" in brightness.

			if transition_mode < 0 or transition_mode > 2:
				return False

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Mode 3: Transition set
				transition_mode
			])
			payload[0] = len(payload)

		elif action == 'set_pixel':
			mode = 2
			# Synthetic action
			x, y, color, brightness = parameters
			pixel = (color, brightness)
			if not Matrix.validate_pixel(pixel):
				return False
			if x > 2 or x < 0 or y > 2 or y < 0:
				return False
			self.current_matrix[int(x)][int(y)] = pixel

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Mode 2: Pixel set
			])
			for x in range(3):
				for y in range(3):
					# brightness in the upper bits, color in the lower, max of 10 on both as 0xAA is 1010 1010 and 1010 is decimal 10
					# chars/figures is 3, which makes sense because 0xAA is 170, or three digits
					payload.append((self.current_matrix[x][y][1] << 4) | self.current_matrix[x][y][0])

			payload[0] = len(payload)

		if payload:
			await self.select_mode_if_not_selected(mode, gatt_payload_writer)
			await gatt_payload_writer(payload)
			return True

		return False
