import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Matrix(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.LPF

		self.port = port

		self.port_id = 0x40
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		self.current_matrix_mode = -1

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 1, False),		# LEV O		Level
			1: ( 1, False),		# COL O		Solid Color
			2: ( 1, False),		# PIX O		Pixel set
			3: ( 1, False)		# TRANS		Set transistion
		}

		self.current_matrix = Matrix.blank_matrix()

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

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

	# Switch the mode by unsubscribing to the mode you want
	# If a change occurs (and a unsubscribe needs to be sent), return True
	def switch_matrix_mode(self, action):
		if action == 'set_level':
			if self.current_matrix_mode != 0:
				self.current_matrix_mode = 0
				return True
		elif action == 'set_color':
			if self.current_matrix_mode != 1:
				self.current_matrix_mode = 1
				return True
		elif action == 'set_pixels':
			if self.current_matrix_mode != 2:
				self.current_matrix_mode = 2
				return True
		elif action == 'set_transition':
			if self.current_matrix_mode != 3:
				self.current_matrix_mode = 3
				return True

		return False

	def send_message(self, message):
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]
		ret_message = None

		if action == 'set_level':
			mode = 0
			level = int(parameters[0])

			if level < 0 or level > 9:
				return

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
			ret_message = { 'gatt_send': (payload,) }

		elif action == 'set_color':
			mode = 1

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
				0x1,	# Mode 1: Color set
				color
			])
			payload[0] = len(payload)
			ret_message = { 'gatt_send': (payload,) }

		elif action == 'set_pixels':
			mode = 2

			new_matrix = parameters[0]
			if not Matrix.validate_matrix(new_matrix):
				return None
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
			ret_message = { 'gatt_send': (payload,) }

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
				return

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
			ret_message = { 'gatt_send': (payload,) }

		elif action == 'set_pixel':
			# Synthetic action
			x, y, color, brightness = parameters
			pixel = (color, brightness)
			if not Matrix.validate_pixel(pixel):
				return None
			if x > 2 or x < 0 or y > 2 or y < 0:
				return None
			self.current_matrix[int(x)][int(y)] = pixel

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
			ret_message = { 'gatt_send': (payload,) }
			# Total hackjob
			action = 'set_pixels'

		if ret_message:
			if self.switch_matrix_mode(action):
				mode_switch_payload = self.gatt_payload_for_subscribe(action, False)
				ret_message = { 'gatt_send': (mode_switch_payload, payload) }
			return ret_message

		return None

	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation

		# Port Input Format Setup (Single) message
		# Sending this results in port_input_format_single response

		if self.current_matrix_mode == -1:
			# This should only happen if you call this function directly, which you shouldn't be doing
			# The play_* messages should make sure it gets set
			# FIXME: However, this points out an absurdity of using this function for other things!
			print("DON'T SUBSCRIBE TO THIS")
			switch_matrix_mode(message_type)

		payload = bytearray()

		payload.extend([
			0x0A,		# length
			0x00,
			0x41,		# Port input format (single)
			self.port,	# port
			self.current_matrix_mode,
		])

		# delta interval (uint32)
		# 5 is what was suggested by https://github.com/salendron/pyLegoMario
		# 88010 Controller buttons for +/- DO NOT WORK without a delta of zero.
		# Amusingly, this is strongly _not_ recommended by the LEGO docs
		# Kind of makes sense, though, since they are discrete (and debounced, I assume)
		delta_int = self.mode_subs[self.current_matrix_mode][0]
		payload.extend(delta_int.to_bytes(4,byteorder='little',signed=False))

		if should_subscribe:
			payload.append(0x1)		# notification enable
		else:
			payload.append(0x0)		# notification disable
		#print(" ".join(hex(n) for n in payload))

		return payload