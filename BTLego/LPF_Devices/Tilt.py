import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Tilt(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.LPF

		self.port = port

		self.port_id = 0x22
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		# Probed count
		self.mode_count = -1	# Default unprobed

		# Per the literature:
		# "detect seven different types of orientation:"
		# "Tilt This Way, Tilt That Way, Tilt Up, Tilt Down, No Tilt, Any Tilt, and Shake"
		# https://education.lego.com/v3/assets/blt293eea581807678a/blt87521f32a1f96bff/5f88043c18967612e58a6a00/toolbox-en-us-v1.pdf
		# "Left" is "show the bottom" if the cord is pointed away from you
		# Therefore "right" is "show the top" when cord is pointed away, lego text upside down
		# THEREFORE the correct orientation is cord towards you for L/R to make sense
		# "Tilt down" with the 2x non cord end pointed down is referenced in one of the WeDo2 instructional tutorials

		# Mode 0:
		#	Raw integers.  Use this when you think I have just messed up the data
		#	translation because I wanted negative pitch to be pointing down
		# Mode 1:
		#	Brick in neutral position
		#		negative roll is left, positive is right
		#		negative pitch is down, positive is up
		# Mode 2: (FIXME)
		#	Wire to Left in front of you, same translations
		self.angle_mode = 1

		self.generated_message_types = (
			'angle',
		)

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 5, False),		# LPF2-ANGLE
			1: ( 5, False),		# LPF2-TILT
			2: ( 5, False),		# LPF2-CRASH
			3: ( 5, False),		# LPF2-CAL
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def decode_pvs(self, port, data):
		if port != self.port:
			return None

		if len(data) == 2:
			# I'm sure there's some clever way to do this and I'm just... not
			# And now I'm not even using it anymore and I won't delete it
			def unsigned_to_signed(lpf_uint8):
				sign = lpf_uint8 >> 7
				absolute = lpf_uint8 ^ 128
				if sign:
					return -absolute
				return absolute

			# Doesn't detect yaw (brick just spinning on a table, flat)
			roll = data[0]
			pitch = data[1]

			if self.angle_mode == 0:
				return ('angle','raw',(roll, pitch))
			elif self.angle_mode == 1:
				zero_roll = data[0]
				if zero_roll > 127:
					zero_roll = -(255-data[0])

				zero_pitch = data[1]
				if zero_pitch > 127:
					zero_pitch = (255-data[1])
				else:
					zero_pitch = -zero_pitch

				return ('angle','zeroed',(zero_roll, zero_pitch))

		return None

	def set_subscribe(self, message_type, should_subscribe):

		mode_for_message_type = -1
		if message_type == 'angle':
			mode_for_message_type = 0

		if mode_for_message_type > -1:
			self.mode_subs[mode_for_message_type] = (self.mode_subs[mode_for_message_type][0], should_subscribe)
			return True

		return False

	def PIFSetup_data_for_message_type(self, message_type):
		# return 4-item array [port, mode, delta interval, subscribe on/off]
		# Base class returns nothing
		# FIXME: use abc

		mode = -1
		if message_type == 'angle':
			mode = 0
		else:
			return None

		return (self.port, mode, *self.mode_subs[mode], )

	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation

		# Port Input Format Setup (Single) message
		# Sending this results in port_input_format_single response

		mode = -1
		if message_type == 'angle':
			mode = 0

		payload = bytearray()
		if mode > -1:
			payload.extend([
				0x0A,		# length
				0x00,
				0x41,		# Port input format (single)
				self.port,	# port
				mode,
			])

			# delta interval (uint32)
			# 5 is what was suggested by https://github.com/salendron/pyLegoMario
			# 88010 Controller buttons for +/- DO NOT WORK without a delta of zero.
			# Amusingly, this is strongly _not_ recommended by the LEGO docs
			# Kind of makes sense, though, since they are discrete (and debounced, I assume)
			delta_int = self.mode_subs[mode][0]
			payload.extend(delta_int.to_bytes(4,byteorder='little',signed=False))

			if should_subscribe:
				payload.append(0x1)		# notification enable
			else:
				payload.append(0x0)		# notification disable
			#print(" ".join(hex(n) for n in payload))

		return payload