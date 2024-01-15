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
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x2a
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# Hmm, why, again?
		self.delta_interval = 1

		self.current_beeper_mode = -1

		# FIXME: Don't use the state integer, use this! (yeah, but it's easier than searching...)
		# These are "negative subscribe to set" modes.  See: RGB (similar).
		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'TONE', ()],		# Tones (high/med/low)
			1: [ self.delta_interval, False, 'SOUND', ()],	# Sounds (from the default interaction mode)
			2: [ self.delta_interval, False, 'UI SND', ()]	# Beeps the UI typically makes
		}

	# Switch the mode by unsubscribing to the mode you want
	# If action is valid, return True
	async def switch_beeper_mode(self, action, gatt_payload_writer):
		if action == 'play_tone':
			if self.current_beeper_mode != 0:
				self.current_beeper_mode = 0
				await self.PIF_single_setup(self.current_beeper_mode, False, gatt_payload_writer)
			return True
		elif action == 'play_sound':
			if self.current_beeper_mode != 1:
				self.current_beeper_mode = 1
				await self.PIF_single_setup(self.current_beeper_mode, False, gatt_payload_writer)
			return True
		elif action == 'play_beep':
			if self.current_beeper_mode != 2:
				self.current_beeper_mode = 2
				await self.PIF_single_setup(self.current_beeper_mode, False, gatt_payload_writer)
			return True
		return False

	async def send_message(self, message, gatt_payload_writer):
		# ( action, (parameters,) )
		action = message[0]
		parameters = message[1]

		noise_id = -1
		if not await self.switch_beeper_mode(action, gatt_payload_writer):
			return False

		if action == 'play_tone':
			noise_id = int(parameters[0])
			if noise_id not in self.tone_numbers:
				return False

		if action == 'play_sound':
			noise_id = int(parameters[0])
			if noise_id not in self.sound_numbers:
				return False

		if action == 'play_beep':
			noise_id = int(parameters[0])
			if noise_id not in self.ui_beep_numbers:
				return False

		if noise_id != -1:
			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
						# Node poweredup and legoino use 0x11 here always
				0x51,	# Subcommand: WriteDirectModeData
				self.current_beeper_mode,
				noise_id
			])
			payload[0] = len(payload)

			await gatt_payload_writer(payload)
			return True

		return False
