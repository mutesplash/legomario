import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Mario_Pants(LPF_Device):

	# Read the pins facing you with MSB on the left (Mario's right)
	# Some pants codes simply do not register.  May be some debouncing or max pin-down circuitry
	pants_codes = {
		0x0:'no',			# 000 000	Sometimes mario registers 0x2 as no pants, might be a pin problem?
		0x1:'vacuum',		# 000 001	Poltergust
		0x2:'no',			# 000 010	Just cover the case and pretend it's normal, who wants to get weird messages and debug them. When you actually PUSH pin 1 (0x2), you get the update icon
		0x3:'bee',			# 000 011	Acts strange and won't send messages when these pants are on.  Needs more testing
#		0x4:'?4?',			# 000 100
		0x5:'luigi',		# 000 101
		0x6:'frog',			# 000 110
							# 000 111
#		0x8:'?8?',			# 001 000	does nothing and doesn't trigger the update icon, perhaps a hidden trigger?  Might also be poltergust?
		0x9:'vacuum_button',# 001 001	Poltergust. Seems to not matter which one is the toggle!
		0xa:'tanooki',		# 001 010	Leaf icon
							# 001 011
		0xc:'propeller',	# 001 100
#		0xd:'?13?',			# 001 101
#		0xe:'?14?',			# 001 110
#		0xf:'?15?',			# 001 111
#		0x10:'?16?',		# 010 000
		0x11:'cat',			# 010 001	Bell icon
		0x12:'fire',		# 010 010
							# 010 011
		0x14:'penguin',		# 010 100
							# 010 101
#		0x16:'22?',			# 010 110
							# 010 111
		0x18:'dress',		# 011 000
#		0x19				# 011 001	What the heck is this?  Mario likes to put these "on" after getting disconnected from multiplayer.  Sometimes it's the cat pants too! (which seems like a bit-flip error)
#		0x1a:'26?',			# 011 010
							# 011 011
#		0x1c:'28?',			# 011 100
							# 011 101
							# 011 110
							# 011 111
		0x20:'mario',		# 100 000	Because who has time to deal with errata... doesn't seem to be the SAME pin problem,  When you actually PUSH pin 5 (0x20), you get the update icon
		0x21:'mario',		# 100 001	Mario pants.  Sometimes mario registers 0x20 as mario pants, might be a pin problem?
		0x22:'builder',		# 100 010
		0x23:'ice',			# 100 011	Ice flower icon
#		0x24:'36?',			# 100 100
#		0x25:'37?',			# 100 101
#		0x26:'38?',			# 100 110
							# 100 111
#		0x28:'40?',			# 101 000
							# 101 001
		0x2a:'cat'			# 101 010	Bell icon. Peach's cat pants
							# 101 011
#		0x2c:'44?',			# 101 100
							# 101 101
							# 101 110
							# 110 111
#		0x30:'48?',			# 110 000
							# 110 001
							# 110 010
							# 110 011
							# 110 100
							# 110 101
							# 110 110
							# 110 111
#		0x38:'?56?'			# 111 000
	}

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x4a
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'PANT', ('pants',)]
		}

	def mario_pants_to_string(mariobyte):
		if mariobyte in Mario_Pants.pants_codes:
			return Mario_Pants.pants_codes[mariobyte]
		else:
			return 'unknown('+str(hex(mariobyte))+')'

	def decode_pvs(self, port, data):
		if port != self.port:
			return None

		if len(data) == 1:
			if data[0] in self.pants_codes:
				return ('pants','pants',data[0])
			else:
				return ('pants','unknown', data[0])
		else:
			return ('unknown', " UNKNOWN PANTS DATA, WEIRD LENGTH OF "+len(data)+":"+" ".join(hex(n) for n in data))
