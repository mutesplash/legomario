import asyncio
from enum import IntEnum

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Vision(LPF_Device):

	# Port B for Blue
	class Port(IntEnum):
		RED = 0x0
		BLUE = 0x1
		A = 0x0
		B = 0x1

	class IR_Mode(IntEnum):
		Extended = 0x0
		ComboDirect = 0x1
		SinglePinContinuous = 0x2	# "reserved" in RC v1.2
		SinglePinTimeout = 0x3		# "reserved" in RC v1.2
		SingleOutput = 0x4			# Has to be ORed with the sub-mode (PWM/CSTID) and the output port (Red/Blue)
		# Also ComboPWM that has to be set with Escape

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		self.port_id = 0x25
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self._ir_toggle = 0x0	# Can't determine what this does, from the docs
		self._ir_address = 0x0	# 0x0 for default PoweredUp or 0x1 for 'extra' space

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'COLOR', ()],		# 0 - 0xA, 3 figures means it has a decimal or signed?
			1: [ self.delta_interval, False, 'PROX', ()],
			2: [ self.delta_interval, False, 'COUNT', ()],
			3: [ self.delta_interval, False, 'REFLT', ()],
			4: [ self.delta_interval, False, 'AMBI', ()],
			5: [ self.delta_interval, False, 'COL O', ()],
			6: [ self.delta_interval, False, 'RGB I', ()],
			7: [ self.delta_interval, False, 'IR Tx', ()],
			8: [ -1, False, 'SPEC 1', ()],	# Specified to have no I/O direction
			9: [ self.delta_interval, False, 'DEBUG', ()],
			10: [ self.delta_interval, False, 'CALIB', ()]
		}

	def ir_port_to_int(port):
		"""
		Converts the Port IntEnum, a single character port letter, or an integer
		into a valid port number for use with IR bit packing functions

		Port B is Blue on the IR Receiver, which is good, because that makes sense.
		"""
		output_port = -1
		if isinstance(port, Vision.Port):
			output_port = int(port)
		elif isinstance(port, str):
			if port == 'A' or port == 'a':
				output_port = 0x0
			elif port == 'B' or port == 'b':
				output_port = 0x1
		elif isinstance(port, int):
			if port == 0x0 or port == 0x1:
				output_port = int(port)
		return output_port

	async def send_message(self, message, gatt_payload_writer):
		processed = await super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]

		# I don't know what the toggle is for, but, might as well expose it
		if action == 'set_ir_toggle':
			# ( int )
			if parameters[0]:
				self._ir_toggle = 0x1
			else:
				self._ir_toggle = 0x0
			return True

		# I don't know what you'd do with the "extra" address space but here it is
		elif action == 'set_ir_extra_space':
			# ( int )
			if parameters[0]:
				self._ir_address = 0x1
			else:
				self._ir_address = 0x0
			return True

		# There's no set_ir_channel here because if you've got multiple receivers
		# I'm thinking having to manage that in this device's state would get out
		# of hand quickly.  I don't know what the the address space and the toggle
		# do so making it state and letting the user deal with it will be fine... for now

		elif action == 'set_ir_sop':
			# ( int, str/int/idk, int )
			channel, port, action = parameters
			payload = self.ir_payload_sop(channel, port, action)
			if payload:
				await self.select_mode_if_not_selected(7, gatt_payload_writer)
				await gatt_payload_writer(payload)
				return True

		elif action == 'set_ir_so_cstid':
			# ( int, str/int/idk, int )
			channel, port, action = parameters
			payload = self.ir_payload_socstid(channel, port, action)
			if payload:
				await self.select_mode_if_not_selected(7, gatt_payload_writer)
				await gatt_payload_writer(payload)
				return True

		elif action == 'set_ir_combo_pwm':
			# ( int, int, int )
			channel, a_mode, b_mode = parameters
			payload = self.ir_payload_combo_pwm(channel, a_mode, b_mode)
			if payload:
				await self.select_mode_if_not_selected(7, gatt_payload_writer)
				await gatt_payload_writer(payload)
				return True

		elif action == 'set_ir_combo_direct':
			# ( int, int, int )
			channel, a_output, b_output = parameters
			# FIXME: Why are these "outputs" instead of "modes" compared to combo PWM?
			# And just because the documents list them that way is not a good reason
			payload = self.ir_payload_combo_direct(channel, a_output, b_output)
			if payload:
				await self.select_mode_if_not_selected(7, gatt_payload_writer)
				await gatt_payload_writer(payload)
				return True

		elif action == 'set_ir_combo_extended':
			# ( int, int )
			channel, mode = parameters
			payload = self.ir_payload_extended(channel, mode)
			if payload:
				await self.select_mode_if_not_selected(7, gatt_payload_writer)
				await gatt_payload_writer(payload)
				return True

		elif action == 'set_ir_single_pin':
			# ( int, int/str/idk, int, int, int )
			channel, port, pin, mode, timeout = parameters
			payload = self.ir_payload_single_pin(channel, port, pin, mode, timeout)
			if payload:
				await self.select_mode_if_not_selected(7, gatt_payload_writer)
				await gatt_payload_writer(payload)
				return True

		elif action == 'set_mode':
			# ( int, )
			mode = int(parameters[0])
			if mode in self.mode_subs:
				self._selected_mode = mode
			else:
				return False
			return await self.PIF_single_setup(self._selected_mode, False, gatt_payload_writer)

		return False

	def ir_payload_sop(self, channel, port, mode_action):
		"""
		Send an IR message via Power Functions RC Protocol in Single Output PWM mode

		PF IR RC Protocol documented at https://www.philohome.com/pf/pf.htm

		Valid values for mode are:
		0x0: Float output
		0x1: Forward/Clockwise at speed 1
		0x2: Forward/Clockwise at speed 2
		0x3: Forward/Clockwise at speed 3
		0x4: Forward/Clockwise at speed 4
		0x5: Forward/Clockwise at speed 5
		0x6: Forward/Clockwise at speed 6
		0x7: Forward/Clockwise at speed 7
		0x8: Brake (then float v1.20)
		0x9: Backwards/Counterclockwise at speed 7
		0xA: Backwards/Counterclockwise at speed 6
		0xB: Backwards/Counterclockwise at speed 5
		0xC: Backwards/Counterclockwise at speed 4
		0xD: Backwards/Counterclockwise at speed 3
		0xE: Backwards/Counterclockwise at speed 2
		0xF: Backwards/Counterclockwise at speed 1

		:param channel: 0-3 which maps to 1-4 on the device
		:param port: Anything ir_port_to_int(port) will parse
		:param mode: 0-15 indicating the port's mode to set
		"""

		# I can relicense my own code...

		escape_modeselect = 0x0
		escape = escape_modeselect

		ir_mode = int(self.IR_Mode.SingleOutput)

		so_mode_pwm = 0x0
		so_mode = so_mode_pwm

		output_port = Vision.ir_port_to_int(port)
		if output_port == -1:
			return False

		ir_mode = ir_mode | (so_mode << 1) | output_port

		nibble1 = (self._ir_toggle << 3) | (escape << 2) | channel
		nibble2 = (self._ir_address << 3) | ir_mode

		# Mode_action range checked here
		return self._pack_ir_nibbles(nibble1, nibble2, mode_action)

	def ir_payload_socstid(self, channel, port, mode_action):
		"""
		Send an IR message via Power Functions RC Protocol in Single Output Clear/Set/Toggle/Increment/Decrement mode

		PF IR RC Protocol documented at https://www.philohome.com/pf/pf.htm

		Valid values for mode are:
		0x0: Toggle full Clockwise/Forward (Stop to Clockwise, Clockwise to Stop, Counterclockwise to Clockwise)
		0x1: Toggle direction
		0x2: Increment numerical PWM
		0x3: Decrement numerical PWM
		0x4: Increment PWM
		0x5: Decrement PWM
		0x6: Full Clockwise/Forward
		0x7: Full Counterclockwise/Backward
		0x8: Toggle full (defaults to Forward, first)
		0x9: Clear C1 (C1 to High)
		0xA: Set C1 (C1 to Low)
		0xB: Toggle C1
		0xC: Clear C2 (C2 to High)
		0xD: Set C2 (C2 to Low)
		0xE: Toggle C2
		0xF: Toggle full Counterclockwise/Backward (Stop to Clockwise, Counterclockwise to Stop, Clockwise to Counterclockwise)

		:param port: 'A' or 'B'
		:param mode: 0-15 indicating the port's mode to set
		"""
		escape_modeselect = 0x0
		escape = escape_modeselect

		ir_mode = int(self.IR_Mode.SingleOutput)

		so_mode_cstid = 0x1
		so_mode = so_mode_cstid

		output_port = Vision.ir_port_to_int(port)
		if output_port == -1:
			return False

		ir_mode = ir_mode | (so_mode << 1) | output_port

		nibble1 = (self._ir_toggle << 3) | (escape << 2) | channel
		nibble2 = (self._ir_address << 3) | ir_mode

		# mode_action range checked here
		return self._pack_ir_nibbles(nibble1, nibble2, mode_action)

	def ir_payload_combo_pwm(self, channel, port_a_mode, port_b_mode):
		"""
		Send an IR message via Power Functions RC Protocol in Combo PWM mode

		Valid values for the modes are:
		0x0 Float
		0x1 PWM Forward step 1
		0x2 PWM Forward step 2
		0x3 PWM Forward step 3
		0x4 PWM Forward step 4
		0x5 PWM Forward step 5
		0x6 PWM Forward step 6
		0x7 PWM Forward step 7
		0x8 Brake (then float v1.20)
		0x9 PWM Backward step 7
		0xA PWM Backward step 6
		0xB PWM Backward step 5
		0xC PWM Backward step 4
		0xD PWM Backward step 3
		0xE PWM Backward step 2
		0xF PWM Backward step 1

		:param port_b_mode: 0-15 indicating the command to send to port B
		:param port_a_mode: 0-15 indicating the command to send to port A
		"""
		escape_combo_pwm = 0x1
		escape = escape_combo_pwm

		nibble1 = (self._ir_toggle << 3) | (escape << 2) | channel

		# Hey look they're inverted on this call.  That's because the protocol
		# puts B first but why confuse normal people by exposing this.  A,B
		# in all APIs...
		return self._pack_ir_nibbles(nibble1, port_b_mode, port_a_mode)

	def ir_payload_combo_direct(self, channel, port_a_output, port_b_output):
		"""
		Send an IR message via Power Functions RC Protocol in Combo Direct mode

		PF IR RC Protocol documented at https://www.philohome.com/pf/pf.htm

		Valid values for the output variables are:
		0x0: Float output
		0x1: Clockwise/Forward
		0x2: Counterclockwise/Backwards
		0x3: Brake then float

		:param port_b_output: 0-3 indicating the output to send to port B
		:param port_a_output: 0-3 indicating the output to send to port A
		"""
		escape_modeselect = 0x0
		escape = escape_modeselect

		ir_mode = int(self.IR_Mode.ComboDirect)

		nibble1 = (self._ir_toggle << 3) | (escape << 2) | channel
		nibble2 = (self._ir_address << 3) | ir_mode

		if port_b_output > 0x3 or port_a_output > 0x3:
			return False
		if port_b_output < 0x0 or port_a_output < 0x0:
			return False

		nibble3 = (port_b_output << 2) | port_a_output

		return self._pack_ir_nibbles(nibble1, nibble2, nibble3)

	def ir_payload_extended(self, channel, mode_action):
		"""
		Send an IR message via Power Functions RC Protocol in Extended mode

		PF IR RC Protocol documented at https://www.philohome.com/pf/pf.htm

		Valid values for the mode are:
		0x0: Brake Port A (timeout)
		0x1: Increment Speed on Port A
		0x2: Decrement Speed on Port A

		0x4: Toggle Forward/Clockwise/Float on Port B

		0x6: Toggle Address bit
		0x7: Align toggle bit

		:param mode: 0-2,4,6-7
		"""
		escape_modeselect = 0x0
		escape = escape_modeselect

		ir_mode = int(self.IR_Mode.Extended)

		nibble1 = (self._ir_toggle << 3) | (escape << 2) | channel
		nibble2 = (self._ir_address << 3) | ir_mode

		if mode_action < 0x0 or mode_action == 0x3 or mode_action == 0x5 or mode_action > 0x7:
			# f'Bad IR Extended mode {mode_action}'
			return False

		return self._pack_ir_nibbles(nibble1, nibble2, mode_action)

	def ir_payload_single_pin(self, channel, port, pin, mode_action, timeout):
		"""
		Send an IR message via Power Functions RC Protocol in Single Pin mode (Seemingly deprecated)

		PF IR RC Protocol documented at https://www.philohome.com/pf/pf.htm

		Valid values for the mode_action are:
		0x0: No-op
		0x1: Clear
		0x2: Set
		0x3: Toggle

		Note: The unlabeled IR receiver (vs the one labeled V2) has a "firmware bug in Single Pin mode"
		"The V1.1 blinks the green led on startup. The 1.0 just turns on."
		https://www.philohome.com/pfrec/pfrec.htm

		:param port: 'A' or 'B'
		:param pin: 1 or 2
		:param mode_action: 0-3 indicating the pin's mode to set
		:param timeout: True or False
		"""
		escape_mode = 0x0
		escape = escape_mode

		ir_mode = None
		if timeout:
			ir_mode = int(self.IR_Mode.SinglePinTimeout)
		else:
			ir_mode = int(self.IR_Mode.SinglePinContinuous)

		output_port = Vision.ir_port_to_int(port)
		if output_port == -1:
			return False

		if pin != 1 and pin != 2:
			return False
		pin_value = pin - 1

		if mode_action > 0x3 or mode_action < 0x0:
			return False

		nibble1 = (self._ir_toggle << 3) | (escape << 2) | channel
		nibble2 = (self._ir_address << 3) | ir_mode
		nibble3 = (output_port << 3) | (pin_value << 3) | mode_action

		return self._pack_ir_nibbles(nibble1, nibble2, nibble3)

	# Debugging (incomplete... and will probably stay that way)
	def decode_ir_nibbles(nibble1, nibble2, nibble3):
		channel = (nibble1 & 0x3) + 1
		escape = (nibble1 & 0x4) >> 2
		if escape is 0x1:
			escape = "COMBO PWM"
		elif escape is 0x0:
			escape = "MODESELECT"
		toggle = (nibble1 & 0x8) >> 3
		if toggle is 0x1:
			toggle = "YES"
		elif toggle is 0x0:
			toggle = "NO"
		print(f'Channel: {channel}, Escape Mode {escape}, Toggle {toggle} > '+" ".join('{:04b}'.format(nibble1)))
		if escape is "COMBO PWM":
			def print_port_action(p, nibble):
				if nibble == 0x0:
					txt = f'\tPort {p} Float'
				elif nibble == 0x1:
					txt = f'\tPort {p} forward step 1'
				elif nibble == 0x2:
					txt = f'\tPort {p} forward step 2'
				elif nibble == 0x3:
					txt = f'\tPort {p} forward step 3'
				elif nibble == 0x4:
					txt = f'\tPort {p} forward step 4'
				elif nibble == 0x5:
					txt = f'\tPort {p} forward step 5'
				elif nibble == 0x6:
					txt = f'\tPort {p} forward step 6'
				elif nibble == 0x7:
					txt = f'\tPort {p} forward step 7'
				elif nibble == 0x8:
					txt = f'\tPort {p} Brake then float'
				elif nibble == 0x9:
					txt = f'\tPort {p} backward step 7'
				elif nibble == 0xA:
					txt = f'\tPort {p} backward step 6'
				elif nibble == 0xB:
					txt = f'\tPort {p} backward step 5'
				elif nibble == 0xC:
					txt = f'\tPort {p} backward step 4'
				elif nibble == 0xD:
					txt = f'\tPort {p} backward step 3'
				elif nibble == 0xE:
					txt = f'\tPort {p} backward step 2'
				elif nibble == 0xF:
					txt = f'\tPort {p} backward step 1'
				print(txt+' > '+" ".join('{:04b}'.format(nibble)))
			print_port_action("(B)Blue",nibble2)
			print_port_action("(A)Red",nibble3)
		elif escape is "MODESELECT":
			address = (nibble2 & 0x8) >> 3
			if address == 0x0:
				address = '(default)'
			elif address == 0x1:
				address = 'EXTRA'
			mode = nibble2 & 0x7
			textmode = str(mode)
			sop_submode = 'ERR: NOT SET'
			if mode == 0x0:
				mode = 'Extended'
			elif mode == 0x1:
				mode = 'Combo Direct'
			elif mode > 0x3 and mode < 0x8:
				mode = 'Single Output'
				sop_submode = nibble2 & 0x2
				if sop_submode == 0x0:
					sop_submode = 'PWM'
				elif sop_submode == 0x1:
					sop_submode = 'CSTID'
				textmode += f' {sop_submode}'
				output_port = nibble2 & 0x1
				if output_port == 0x0:
					output_port = '(0,A,Red)'
				elif output_port == 0x1:
					output_port = '(1,B,Blue)'
				textmode += f' on port {output_port}'
			print(f'\tAddress {address} Mode: {textmode} > '+" ".join('{:04b}'.format(nibble2)))
			if mode == 'Single Output':
				txt = 'ERR IDK WHAT KIND OF SINGLE OUTPUT'
				if sop_submode is 'PWM':
					if nibble3 == 0x0:
						txt = 'Float'
					elif nibble3 == 0x1:
						txt = 'PWM forward step 1'
					elif nibble3 == 0x2:
						txt = 'PWM forward step 2'
					elif nibble3 == 0x3:
						txt = 'PWM forward step 3'
					elif nibble3 == 0x4:
						txt = 'PWM forward step 4'
					elif nibble3 == 0x5:
						txt = 'PWM forward step 5'
					elif nibble3 == 0x6:
						txt = 'PWM forward step 6'
					elif nibble3 == 0x7:
						txt = 'PWM forward step 7'
					elif nibble3 == 0x8:
						txt = 'Brake then float'
					elif nibble3 == 0x9:
						txt = 'PWM backward step 7'
					elif nibble3 == 0xA:
						txt = 'PWM backward step 6'
					elif nibble3 == 0xB:
						txt = 'PWM backward step 5'
					elif nibble3 == 0xC:
						txt = 'PWM backward step 4'
					elif nibble3 == 0xD:
						txt = 'PWM backward step 3'
					elif nibble3 == 0xE:
						txt = 'PWM backward step 2'
					elif nibble3 == 0xF:
						txt = 'PWM backward step 1'
					else:
						txt = f'ERR NO PWM COMMAND FOR {nibble3}'
				elif sop_submode is 'CSTID':
					if nibble3 == 0x0:
						txt = 'Toggle full forward'
					elif nibble3 == 0x1:
						txt = 'Toggle direction'
					elif nibble3 == 0x2:
						txt = 'Inc. numerical PWM'
					elif nibble3 == 0x3:
						txt = 'Dec. numerical PWM'
					elif nibble3 == 0x4:
						txt = 'Inc. PWM'
					elif nibble3 == 0x5:
						txt = 'Dec. PWM'
					elif nibble3 == 0x6:
						txt = 'Full forward w/timeout'
					elif nibble3 == 0x7:
						txt = 'Full backward w/timeout'
					elif nibble3 == 0x8:
						txt = 'Toggle full fw/bw'
					elif nibble3 == 0x9:
						txt = 'Clear C1'
					elif nibble3 == 0xA:
						txt = 'Set C1'
					elif nibble3 == 0xB:
						txt = 'Toggle C1'
					elif nibble3 == 0xC:
						txt = 'Clear C2'
					elif nibble3 == 0xD:
						txt = 'Set C2'
					elif nibble3 == 0xE:
						txt = 'Toggle C2'
					elif nibble3 == 0xF:
						txt = 'Toggle full backward'
					else:
						txt = f'ERR NO CSTID COMMAND FOR {nibble3}'
				else:
					txt = f'ERR DUNNO SINGLE OUTPUT SUBMODE OF {sop_submode}'
				print(f'\t{txt} > '+" ".join('{:04b}'.format(nibble3)))

		LRC = 0xF ^ nibble1 ^ nibble2 ^ nibble3
		print("\tLRC (unused): "+" ".join('{:04b}'.format(nibble1)))

	def _pack_ir_nibbles(self, nibble1, nibble2, nibble3):

		# I COULD let people shoot themselves in the foot by using self._selected_mode
		# or I could just set this to the correct value and hope that _I_ jam
		# await select_mode_if_not_selected(7) in front of any IR payload write
		mode = 7

		if nibble1 > 0xF or nibble2 > 0xF or nibble3 > 0xF:
			return False
		if nibble1 < 0x0 or nibble2 < 0x0 or nibble3 < 0x0:
			return False

		data = bytearray(2)
		data[0] = ( nibble2 << 4) | nibble3
		# LRC calculation makes no difference: Upper bits are ignored
		data[1] = nibble1

		#Vision.decode_ir_nibbles(nibble1, nibble2, nibble3)
		# print(" ".join('{:04b}'.format(nibble1)))
		# print(" ".join('{:04b}'.format(nibble2)))
		# print(" ".join('{:04b}'.format(nibble3)))
		# print(" ".join('{:08b}'.format(n) for n in data))

		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x81,	# Command: port_output_command
			# end header
			self.port,
			0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
					# Node poweredup and legoino use 0x11 here always
			0x51,	# Subcommand: WriteDirectModeData
			mode,	# Appendix 6.1 specifies that the desired mode goes here and
					# the rest of the payload is mode specific, in this case, the
					# PF RC IR Protocol bytes
		])
		payload.extend(data)
		payload[0] = len(payload)

		return payload
