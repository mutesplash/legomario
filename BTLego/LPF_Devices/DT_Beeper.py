import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class DT_Beeper(LPF_Device):

	# Beeper Mode 0
	tone_numbers = {
		0x0:'none',
		0x3:'low',		# White tile, light off
		0x9:'medium',
		0xa:'high'		# White tile, light on
	}

	# Beeper Mode 1
	sound_numbers = {
		0x0:'none',
		0x3:'brake',	# Red tile
		0x5:'tune',		# ? what makes THIS ?
		0x7:'water',	# pretend_default_blue_tile
		0x9:'whistle',	# Yellow tile
		0xa:'horn',		# pretend_default_green_tile
	}

	# Beeper Mode 2
	ui_beep_numbers = {
		0x0:'none',
		0x1:'beep beep (low)',
		0x2:'beep',
		0x3:'turn off',
		#0x4 invalid
		0x5:'bluetooth disconnect',
		#0x6 invalid
		0x7:'bluetooth connect',
		#0x8 invalid
		0x9:'turn on',
		0xa:'beep beep beep',
	}

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.FIXED

		self.port = port

		self.port_id = 0x2a
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		self.current_beeper_mode = -1

		# Probed count
		self.mode_count = -1	# Default unprobed

		# FIXME: Don't use the state integer, use this!
		# These are "negative subscribe to set" modes.  See: RGB (similar).
		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 1, False),		# TONE		Tones (high/med/low)
			1: ( 1, False),		# SOUND		Sounds (from the default interaction mode)
			2: ( 1, False)		# UI SND	Beeps the UI typically makes
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	# Switch the mode by unsubscribing to the mode you want
	# If a change occurs (and a unsubscribe needs to be sent), return True
	def switch_beeper_mode(self, action):
		if action == 'play_tone':
			if self.current_beeper_mode != 0:
				self.current_beeper_mode = 0
				return True
		elif action == 'play_sound':
			if self.current_beeper_mode != 1:
				self.current_beeper_mode = 1
				return True
		elif action == 'play_beep':
			if self.current_beeper_mode != 2:
				self.current_beeper_mode = 2
				return True

		return False

	def send_message(self, message):
		# ( action, (parameters,) )
		action = message[0]
		parameters = message[1]

		mode = -1
		noise_id = -1
		did_switch_beeper_mode = self.switch_beeper_mode(action)

		if action == 'play_tone':
			mode = 0
			noise_id = int(parameters[0])
			if noise_id not in self.tone_numbers:
				return None

		if action == 'play_sound':
			mode = 1
			noise_id = int(parameters[0])
			if noise_id not in self.sound_numbers:
				return None


		if action == 'play_beep':
			mode = 2
			noise_id = int(parameters[0])
			if noise_id not in self.ui_beep_numbers:
				return None

		if mode != -1 and noise_id != -1:

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
						# Node poweredup and legoino use 0x11 here always
				0x51,	# Subcommand: WriteDirectModeData
				mode,
				noise_id
			])
			payload[0] = len(payload)
			ret_message = { 'gatt_send': (payload,) }

			if did_switch_beeper_mode:
				# You _unsubscribe_ to the mode to switch to it
				# message_type doesn't really matter
				mode_switch_payload = self.gatt_payload_for_subscribe('play_tone', False)
				ret_message = { 'gatt_send': (mode_switch_payload, payload) }

			return ret_message

		return None

	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation

		# Port Input Format Setup (Single) message
		# Sending this results in port_input_format_single response

		payload = bytearray()
		if self.current_beeper_mode == -1:
			# This should only happen if you call this function directly, which you shouldn't be doing
			# The play_* messages should make sure it gets set
			# FIXME: However, this points out an absurdity of using this function for other things!
			print("DON'T SUBSCRIBE TO THIS")
			switch_beeper_mode(message_type)

		payload.extend([
			0x0A,		# length
			0x00,
			0x41,		# Port input format (single)
			self.port,	# port
			self.current_beeper_mode,
		])

		# delta interval (uint32)
		# 5 is what was suggested by https://github.com/salendron/pyLegoMario
		# 88010 Controller buttons for +/- DO NOT WORK without a delta of zero.
		# Amusingly, this is strongly _not_ recommended by the LEGO docs
		# Kind of makes sense, though, since they are discrete (and debounced, I assume)
		delta_int = self.mode_subs[self.current_beeper_mode][0]
		payload.extend(delta_int.to_bytes(4,byteorder='little',signed=False))

		if should_subscribe:
			payload.append(0x1)		# notification enable
		else:
			payload.append(0x0)		# notification disable
		#print(" ".join(hex(n) for n in payload))

		return payload

