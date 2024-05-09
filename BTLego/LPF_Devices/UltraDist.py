import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class UltraDist(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		self.port_id = 0x3e
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self._use_cm = False	# It's metric, DIY conversion is easy!  Decimals are ugly!  Given the prior statements, I don't care what the symbol in the mode info is!

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'DISTL', ('distance_long',)],	# 	4.0 to 200.0 cm or so  Delta of 1 is too small, use 2
			1: [ self.delta_interval, False, 'DISTS', ('distance_short',)],	#	4.0 to 32.0 cm or so.  Delta of 1 is too small, use 2
			2: [ self.delta_interval, False, 'SINGL', ()],
			3: [ self.delta_interval, False, 'LISTN', ()],
			4: [ self.delta_interval, False, 'TRAW', ()],	# "uS" Microseconds?
			5: [ self.delta_interval, False, 'LIGHT', ()],
			6: [ self.delta_interval, False, 'PING', ()],
			7: [ self.delta_interval, False, 'ADRAW', ()],
			8: [ -1, False, 'CALIB', ()]	# NO IO
		}

	# When disconnected from the sensor with a T6 torx, the black housing does not register on the hub
	# I guess you can talk directly to the LPF2 port over the 8-pin connector

	def decode_pvs(self, port, data):
		if port != self.port:
			return None

		mode = self._selected_mode

		# I'm just going to continue copying this until it gets me into major
		# trouble with a race condition I'm not expecting
		if not self.outstanding_requests.empty():
			mode = self.outstanding_requests.get()

		if mode == 0:
			if len(data) == 2:
				# Port info says "CM" and decimals is 1.  Why not just mm then?
				# 5 figures covers 65535, which is "infinity".
				# "Figures" must not cover decimals
				distance = int.from_bytes(data, byteorder="little")
				if distance == 65535:
					# debatable if I should be doing this...
					distance = -1
				else:
					if self._use_cm:
						# Convert to cm from mm integer
						distance = distance / 10
				return ('ultrasonic','distance_long', distance)

		elif mode == 1:
			if len(data) == 2:
				distance = int.from_bytes(data, byteorder="little")
				if distance == 65535:
					# debatable if I should be doing this...
					distance = -1
				else:
					if self._use_cm:
						# Convert to cm from mm integer
						distance = distance / 10
				return ('ultrasonic','distance_short', distance)

		elif mode == 4:
			if len(data) == 4:
				wat_dis = int.from_bytes(data, byteorder="little")
				# First 27 bits set, so that's weird
				# What are the upper five for?
				if wat_dis == 134217727:
					wat_dis = -1
				return ('ultrasonic','t_raw', wat_dis)

	async def send_message(self, message, gatt_payload_writer):
		processed = await super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]

		if action == 'use_mm':
			self._use_cm = False
			return True
		elif action == 'use_cm':
			self._use_cm = True
			return True

		if action == 'leds':
			# Relative to a theoretical robot: ie: right would be their right eye
			right_upper, left_upper, right_lower, left_lower = parameters

			def rangecheck(led_power):
				if led_power > 100:
					led_power = 100
				if led_power < 0:
					led_power = 0
				return led_power

			right_upper = int(rangecheck(right_upper))
			left_upper = int(rangecheck(left_upper))
			right_lower = int(rangecheck(right_lower))
			left_lower = int(rangecheck(left_lower))

			mode = 5

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Appendix 6.1
				right_upper,
				left_upper,
				right_lower,
				left_lower
			])
			payload[0] = len(payload)
			await gatt_payload_writer(payload)
			return True

		elif action == 'ping':

			mode = 6
			# I don't know what this does, but the mode information says you can
			# stuff 8 bits into it and it doesn't really complain about it
			ping_data = parameters[0]

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Appendix 6.1
				ping_data
			])
			payload[0] = len(payload)
			await gatt_payload_writer(payload)
			return True


		return False
