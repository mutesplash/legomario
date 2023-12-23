import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Mario_Tilt(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.FIXED

		self.port = port

		self.port_id = 0x47
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.generated_message_types = (
			'motion',
			'gesture'
		)

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 5, False),		# RAW
			1: ( 5, False),		# GEST (probably more useful)
		}
		# Mode 0: RAW
		# Mode 1: GEST (probably more useful)
#		elif message_type == 'motion':
#			await self._set_port_subscriptions([[self.device_ports[Decoder.io_type_id['MARIO IMU']],0,5,should_subscribe]])
#		elif message_type == 'gesture':
#			await self._set_port_subscriptions([[self.device_ports[Decoder.io_type_id['MARIO IMU']],1,5,should_subscribe]])

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def decode_pvs(self, port, data):
		if port != self.port:
			return None

		# FIXME: Doesn't really verify if you subscribed to the data before sending it

#	# IMU Mode 0,1
#	def _decode_accel_data(self, data):
		# The "default" value is around 32, which seems like g at 32 ft/s^2
		# But when you flip a sensor 180, it's -15
		# "Waggle" is probably detected by rapid accelerometer events that don't meaningfully change the values

		# RAW: Mode 0
		if len(data) == 3:
			# Put mario on his right side and he will register ~32
			lr_accel = int(data[0])
			if lr_accel > 127:
				lr_accel = -(127-(lr_accel>>1))

			# Stand mario up to register ~32
			ud_accel = int(data[1])
			if ud_accel > 127:
				ud_accel = -(127-(ud_accel>>1))

			# Put mario on his back and he will register ~32
			fb_accel = int(data[2])
			if fb_accel > 127:
				fb_accel = -(127-(fb_accel>>1))

			# FIXME: No, not a good name, more like angle
			return ( 'motion', 'signed_triplet', ( lr_accel, fb_accel, ud_accel ) )

		# GEST: Mode 1
		# 0x8 0x0 0x45 0x0 [ 0x0 0x80 0x0 0x80 ]
		elif len(data) == 4:

			little_32b_int = int.from_bytes(data, byteorder="little", signed=False)
			if not little_32b_int == 0x0:
				#print("full: "+'{:032b}'.format(little_32b_int))

				first_16b_int = int.from_bytes(data[:2], byteorder="little", signed=False)
				last_16b_int = int.from_bytes(data[2:], byteorder="little", signed=False)
				if (first_16b_int != last_16b_int):
					print("split ints: "+'{:016b}'.format(first_16b_int)+'_'+'{:016b}'.format(last_16b_int))
				else:
					# https://github.com/djipko/legomario.py/blob/master/legomario.py
					# https://github.com/benthomasson/legomario/commit/16670878fb0be28481733fefee7754adc8820e1a

					detect_bit = True
					#print("matched ints: "+'{:016b}'.format(first_16b_int))

					# Walk						0000 0000_0x00000x
					# Odd that I've never seen 0x1 or 0x40 by themselves
					# djipko claims 0x1 is bump
					# Just walk the player side to side on a surface
					# Can also generate by wobbling a rail car front to back within it's limits
					PLAYER_WALK					= 0x40 + 0x1

					# Seen live after a slam 	0000 0000_000000x0
					PLAYER_DUNNO_2				= 0x2

					# Seen live	after jump		0000 0000_00000100
					# benthomasson (fly) if paired with direction change 0x1000
					PLAYER_DUNNO_4				= 0x4

					# Flip						0000 0000_0000x000	benthomasson (hardshake)
					# Do a flip on peach's swing (BRYVG) and it will make a magic sound
					# and emit this gesture.  Doesn't seem to matter which direction (front or back)
					# Sideways does not work
					PLAYER_FLIP					= 0x8

					# Shake						0000 0000_00010000	djipko (shake), benthomasson (flip) (if split and lower are 0x0?)
					# benthomasson has "flip" as 0x100000 in a 32-bit int, which is 0x10 if the high bits are actually a 16-bit int
					#	This showed up on peach as a matched set of 0x10
					# Use the peach swing quickly
					# Enough of these make the player "dizzy"
					PLAYER_SHAKE				= 0x10

					# Tornado spin				0000 0000_00100000	benthomasson (spin)
					# Hold the player upright in your hand, put your elbow on a table as a pivot,
					# then move the player around in a circle (~4in diameter)
					# Usually also makes them dizzy
					# Doesn't seem to work inverted (holding the player above the table with your elbow in the air)
					# Not sure how this would be generated in a set
					PLAYER_TORNADO				= 0x20

					# 0x40? Never seen

					# 0x80? Never seen

					# Turn (clockwise)			0000 000x_00000000	djipko (turning)
					PLAYER_CLOCKWISE			= 0x100

					# Move quickly				0000 00x0_00000000	djipko (fastmove)
					# Peach swing when done moderately quickly
					# Emitted constantly on the Piranha Plant Power Slide (GRPLB)
					# Triggers for "ouch" on this code seem to be anything that is not PLAYER_JUMP or PLAYER_WALK
					PLAYER_MOVING				= 0x200

					# Disturbed					0000 0x00_00000000	djipko (translation)
					PLAYER_DISTURBED			= 0x400

					# Crash	(violent stop)		0000 x000_00000000	djipko (high fall crash)
					# Side to side shaking on a rail generates this
					PLAYER_CRASH				= 0x800

					# Sudden stop				000x 0000_00000000	djipko (direction change)
					# Easy to replicate on Piranha Plant Power Slide (GRPLB)
					# Ride Peach's swing sideways to constantly generate, so detection seems directionally biased
					# Moving up and down quickly generates it a lot
					PLAYER_SUDDEN_STOP			= 0x1000

					# Inverse turn				00x0 000x_00000000	djipko (reverse)
					PLAYER_INVERT_TURN			= 0x2000 # + 0x100 Mask to check only if turn inverts

					# Flying roll				0x00 0000_00000000	benthomasson (roll)
					# Player needs to be horizontal like they're flying and then quickly rolled
					PLAYER_ROLL					= 0x4000

					# Jump						x000 0000_00000000	djipko (jump)
					PLAYER_JUMP					= 0x8000

					# "Throw" or "tip" is MOVE then JUMP?  Mario's internal code for dealing with
					# throwing turnips or eating cake and fruit seems to not reliably match
					# the bluetooth data, which isn't a new phenomenon...

					# Sometimes mario can return a bunch of nonsense at the same time like, clockwise jump direction change
					# This elif ladder obviously only dones one of them at a time
					# Debating how to message that

					if bool (first_16b_int & PLAYER_CLOCKWISE ):
						if bool (first_16b_int & PLAYER_INVERT_TURN ):
							return ('gesture','turn','counterclockwise')
						else:
							return ('gesture','turn','clockwise')

					elif bool (first_16b_int & PLAYER_DISTURBED ):
						return ('gesture','disturbed',None)

					elif bool (first_16b_int & PLAYER_MOVING ):
						return ('gesture','moving',None)

					elif bool (first_16b_int & PLAYER_JUMP ):
						return ('gesture','jump',None)

					elif bool (first_16b_int & PLAYER_WALK ):
						return ('gesture','walk',None)
						pass

					elif bool (first_16b_int & PLAYER_SHAKE ):
						return ('gesture','shake',None)

					elif bool (first_16b_int & PLAYER_FLIP ):
						return ('gesture','flip',None)

					elif bool (first_16b_int & PLAYER_SUDDEN_STOP ):
						return ('gesture','stop',None)

					elif bool (first_16b_int & PLAYER_CRASH ):
						return ('gesture','crash',None)

					elif bool (first_16b_int & PLAYER_TORNADO ):
						return ('gesture','tornado',None)

					elif bool (first_16b_int & PLAYER_ROLL ):
						return ('gesture','roll',None)

					elif bool (first_16b_int & PLAYER_DUNNO_4 ):
						print("BIT: dunno4?")
						pass

					elif bool (first_16b_int & PLAYER_DUNNO_2 ):
						print("BIT: dunno2?")
						pass

					elif bool (first_16b_int & (0x1 | 0x40 | 0x80) ):
						print("WHAT DID YOU DO?!  matched ints: "+'{:08b}'.format(data[1])+'_'+'{:08b}'.format(data[0]))

					else:
						detect_bit = False
						print("matched ints: "+'{:08b}'.format(data[1])+'_'+'{:08b}'.format(data[0]))

			else:
				# Maybe this is "done?", as sometimes you'll see a bunch of gestures and then this
				#print("ignoring empty gesture")
				return ( None, )

			notes= ""
			if data[0] != data[2]:
				notes += "NOTE:odd mismatch:"
			if data[1] != data[3]:
				notes += "NOTE:even mismatch:"
			if (data[0] and data[1]) or (data[2] and data[3]) or (data[0] and data[3]) or (data[1] and data[2]):
				# "matched ints"
				#notes += "NOTE:dual paring:"
				pass

			if notes:
				print(self.system_type+" gesture data:"+notes+" ".join(hex(n) for n in data),2)

	def set_subscribe(self, message_type, should_subscribe):
		if message_type == 'motion':
			mode_for_message_type = 0
			# Don't change the delta
			self.mode_subs[mode_for_message_type] = (self.mode_subs[mode_for_message_type][0], should_subscribe)
		elif message_type == 'gesture':
			mode_for_message_type = 1
			# Don't change the delta
			self.mode_subs[mode_for_message_type] = (self.mode_subs[mode_for_message_type][0], should_subscribe)
		else:
			return False
		return True

	def PIFSetup_data_for_message_type(self, message_type):
		# return 4-item array [port, mode, delta interval, subscribe on/off]
		# Base class returns nothing
		# FIXME: use abc

		single_mode = -1
		if message_type == 'motion':
			single_mode = 0
		elif message_type == 'gesture':
			single_mode = 1

		if single_mode != -1:
			return (self.port, single_mode, *self.mode_subs[single_mode], )

		return None

	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation

		# Port Input Format Setup (Single) message
		# Sending this results in port_input_format_single response

		payload = bytearray()
		single_mode = -1
		if message_type == 'motion':
			single_mode = 0
		elif message_type == 'gesture':
			single_mode = 1

		if single_mode != -1:
			payload.extend([
				0x0A,		# length
				0x00,
				0x41,		# Port input format (single)
				self.port,	# port
				single_mode,
			])

			# delta interval (uint32)
			# 5 is what was suggested by https://github.com/salendron/pyLegoMario
			# 88010 Controller buttons for +/- DO NOT WORK without a delta of zero.
			# Amusingly, this is strongly _not_ recommended by the LEGO docs
			# Kind of makes sense, though, since they are discrete (and debounced, I assume)
			delta_int = self.mode_subs[single_mode][0]
			payload.extend(delta_int.to_bytes(4,byteorder='little',signed=False))

			if should_subscribe:
				payload.append(0x1)		# notification enable
			else:
				payload.append(0x0)		# notification disable
			#print(" ".join(hex(n) for n in payload))

		return payload
