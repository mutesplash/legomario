import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class RGB(LPF_Device):

	LED_MODE_RGB = 1
	LED_MODE_COLOR = 0

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.FIXED

		self.port = port

		self.port_id = 0x17
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		self.current_led_mode = -1

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.generated_message_types = ( )

		# FIXME: Don't use current_led_mode, use this!
		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 1, False),		# COL O		Color mode: 0 - 0xA
			1: ( 1, False)		# RGB O		RGB Mode: r,g,b (0-255 each)
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def set_subscribe(self, message_type, should_subscribe):
		mode_for_message_type = -1
		if message_type == 'set_color':
			mode_for_message_type = 0
		if message_type == 'set_rgb':
			mode_for_message_type = 1
		else:
			return False

		# Don't change the delta
		self.mode_subs[mode_for_message_type] = (self.mode_subs[mode_for_message_type][0], should_subscribe)
		return True

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

	def send_message(self, message):
		# ( action, (parameters,) )
		action = message[0]
		parameters = message[1]
		ret_message = None

		if action == 'set_color':
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
				0x0,	# Mode 0 "COL O"
				color
			])
			payload[0] = len(payload)
			ret_message = { 'gatt_send': (payload,) }

		elif action == 'set_rgb':
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
				0x1,	# Mode 1 "RGB O"
				red,
				green,
				blue
			])
			payload[0] = len(payload)
			ret_message = { 'gatt_send': (payload,) }

		if ret_message:
			if self.switch_led_mode(action):
				# Hat tip to legoino (Lpf2Hub.cpp) for noting that you have to do the port input format setup
				# to change the input mode instead of just yolo sending it (because that doesn't work)
				# I guess the docs _kind of_ say that but they'e not really easy to interpret
				# You _unsubscribe_ to the mode to switch to it
				mode_switch_payload = self.gatt_payload_for_subscribe(action, False)
				ret_message = { 'gatt_send': (mode_switch_payload, payload) }
			return ret_message

		return None

	def PIFSetup_data_for_message_type(self, message_type):
		# return 4-item array [port, mode, delta interval, subscribe on/off]
		# Base class returns nothing
		# FIXME: use abc

		mode = -1
		if message_type == 'set_color':
			mode = 0
		elif message_type == 'set_rgb':
			mode = 1
		else:
			return None

		return (self.port, mode, *self.mode_subs[mode], )

	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation

		# Port Input Format Setup (Single) message
		# Sending this results in port_input_format_single response

		payload = bytearray()

		# You can subscribe to this device, but it doesn't return any useful data.
		# Instead, the subscription data is necessary because sending the port
		# along with the set command in the GATT send is insufficient to specify
		# what you want to happen
		# ( I guess because it has to prepare a buffer since the sizes vary )
		# so you have to "subscribe" in the negative to change the input format.
		# The send commands here put the mode switch before the send data
		# in the gatt_send command
		# SO
		# Internally, the class will request the subscription data for the
		# type of the send, but nobody is supposed to subscribe to it because
		# it's generally useless and will desynchronize the class from the
		# device state
		# DT_Beeper is the same way

		if self.current_led_mode == -1:
			# This should only happen if you call this function directly, which you shouldn't be doing
			# The play_* messages should make sure it gets set
			# FIXME: However, this points out an absurdity of using this function for other things!
			print("DON'T SUBSCRIBE TO THIS")
			switch_matrix_mode(message_type)

		payload.extend([
			0x0A,		# length
			0x00,
			0x41,		# Port input format (single)
			self.port,	# port
			self.current_led_mode,
		])

		# delta interval (uint32)
		# 5 is what was suggested by https://github.com/salendron/pyLegoMario
		# 88010 Controller buttons for +/- DO NOT WORK without a delta of zero.
		# Amusingly, this is strongly _not_ recommended by the LEGO docs
		# Kind of makes sense, though, since they are discrete (and debounced, I assume)
		delta_int = self.mode_subs[self.current_led_mode][0]
		payload.extend(delta_int.to_bytes(4,byteorder='little',signed=False))

		if should_subscribe:
			payload.append(0x1)		# notification enable
		else:
			payload.append(0x0)		# notification disable
		#print(" ".join(hex(n) for n in payload))

		return payload
