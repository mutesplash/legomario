import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class DT_Scanner(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x5b
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ 1, False, 'TAG', ('duplotrain_scantag',)],	# Doesn't scan the tabs, what does it scan?
		}

	def decode_pvs(self, port, data):
		# Mode 0
		if len(data) == 2:
			first_bytes = int.from_bytes(data[0:], byteorder="little")

			if first_bytes == 1:
				# 35962pb04	: White : Sun Icon : Train speed pattern: 0,40,50,60,69
				return ('duplotrain_scantag','tab','white' )
			elif first_bytes == 21:
				# 35962pb03 : X in Circle Icon: Train speed pattern 0,-5,-10,-15,-10,-5,0 ... 95,91,87,83,79,75,72,69
				return ('duplotrain_scantag','tab','red' )

			elif first_bytes == 24:
				# 35962pb05 : Music Note Icon: NO EVENTS, Toots the horn
				return ('duplotrain_scantag','tab','yellow' )

			elif first_bytes == 28:
				# 35962pb02 : Double Arrow Icon: Speed to zero, reverses direction
				return ('duplotrain_scantag','tab','green' )

			elif first_bytes == 119:
				# 35962pb09 : Tree Icon: Speed to zero, plays sounds
				return ('duplotrain_scantag','tab','lime' )

			elif first_bytes == 191:
				# 35962pb13 : Wrench Icon: Train speed pattern: 0,-25,0,25,0,-25,0,25,0
				return ('duplotrain_scantag','tab','bright light orange' )

			elif first_bytes == 321:
				# 35962pb01 : Water Icon: Difficult to scan. Train speed pattern: 0,-50,50,-50,50,-50,50,-50,50,-50,50,55,60,65,69
				return ('duplotrain_scantag','tab','blue' )

			elif first_bytes == 324:
				# 35962pb08 : Star Icon: NO EVENTS, plays sounds for longer than you would expect
				return ('duplotrain_scantag','tab','medium lavender' )

			elif first_bytes == 353:
				# 35962pb10 : House Icon: Speed to zero, plays sounds
				return ('duplotrain_scantag','tab','coral' )

			elif first_bytes == 402:
				# 35962pb12 : Clock Icon: Speed to zero, plays sounds
				return ('duplotrain_scantag','tab','reddish orange' )

			else:
				print(f"UNKNOWN Tab: #{first_bytes}")

				# 35962pb11 : Dark Azure : Water with sheen Icon:
				# 35962pb14 : Bright Green: Lightning Bolt Icon:
				return ('duplotrain_scantag','tag', first_bytes )
