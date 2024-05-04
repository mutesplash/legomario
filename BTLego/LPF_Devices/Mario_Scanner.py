import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from ..MarioScanspace import MarioScanspace

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Mario_Scanner(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x49
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# Can only subscribe to one of these at a time
		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'TAG', ('scanner',)],	# Selected by default when powered-on?
			1: [ self.delta_interval, False, 'RGB', ('rgb',)]

			# FIXME: So, I've slept since I did this.  Some of these things just transmit by default, how will the subscribe_boolean reflect this?
		}

	def decode_pvs(self, port, data):
		if port != self.port:
			return None

		# Mode 0
		if len(data) == 4:

			scantype = None
			if data[2] == 0xff and data[3] == 0xff:
				scantype = 'barcode'
			if data[0] == 0xff and data[1] == 0xff:
				if scantype == 'barcode':
					scantype = 'nothing'
				else:
					scantype = 'color'

			if not scantype:
				return ('unknown', "UNKNOWN SCANNER DATA:"+" ".join(hex(n) for n in data))

			if scantype == 'barcode':
				barcode_int = int.from_bytes(data[0:2], byteorder="little")
				# Max 16-bit signed int, Github Issue #4
				if barcode_int != 32767:
					# Happens when Black is used as a color
					code_info = MarioScanspace.get_code_info(barcode_int)
					return ('scanner','code',(code_info['barcode'], barcode_int))
				else:
					# FIXME: Scanner, error, instead?
					return ('error','message','Scanned malformed code')
			elif scantype == 'color':
				color = MarioScanspace.mario_bytes_to_solid_color(data[2:4])
				return ('scanner','color',color)
			else:
				#scantype == 'nothing':
				return ('notice', 'scanned', 'nothing')

		elif len(data) == 3:
			# This is probably R, G, B based on some basic tests.  Data is not very good, though!
			# Port mode info for RAW, PCT, and SI also seems wrong
			return ('rgb','rgb', (int(data[0]), int(data[1]), int(data[2]) ) )
		else:
			return ('unknown', f'UNKNOWN SCANNER DATA, WEIRD LENGTH OF {len(data)}:'+" ".join(hex(n) for n in data))
