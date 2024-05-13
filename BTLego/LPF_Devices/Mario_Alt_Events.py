import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Mario_Alt_Events(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x55
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'Events', ('alt_event',)]
		}

	def decode_pvs(self, port, data):
		if port != self.port:
			print(f'ERROR: Object port {self.port} does not match bluetooth message port {port}: Refusing to process')
			return None

		if len(data) == 4:
			# Peach goodbye mario
			# 0x2 0x0 0x1 0x0

			# Right after connect, sort of weird connect, though
			# peach  No idea what kind of PVS:port_value_single - port 4: 0x2 0x0 0x1 0x0

			# Luigi goodbye peach
			# 0x2 0x0 0x3 0x0

			action = int.from_bytes(data[:2], byteorder="little")
			if action == 1:
				player = int.from_bytes(data[2:], byteorder="little")
				if player == 1:
					return ('alt_event','multiplayer', ('hello', 'mario'))
				elif player == 2:
					return ('alt_event','multiplayer', ('hello', 'luigi'))
				elif player == 3:
					return ('alt_event','multiplayer', ('hello', 'peach'))
				else:
					return ('unknown', "Unknown hello event for player:"+" ".join(hex(n) for n in data[2:]))

			elif action == 2:
				player = int.from_bytes(data[2:], byteorder="little")
				if player == 1:
					return ('alt_event','multiplayer', ('goodbye', 'mario'))
				elif player == 2:
					return ('alt_event','multiplayer', ('goodbye', 'luigi'))
				elif player == 3:
					return ('alt_event','multiplayer', ('goodbye', 'peach'))
				else:
					return ('unknown', "Unknown goodbye event for player:"+" ".join(hex(n) for n in data[2:]))
			else:
				# Mario/Peach connect
				#UNKNOWN action 1. Alternate event data:0x1 0x0 0x3 0x0
				#UNKNOWN action 4. Alternate event data:0x4 0x0 0x0 0x0
				#UNKNOWN action 11. Alternate event data:0xb 0x0 0x63 0xe8
				#UNKNOWN action 1. Alternate event data:0x1 0x0 0x1 0x0

				# Mario/Peach connect
				#UNKNOWN action 1. Alternate event data:0x1 0x0 0x1 0x0
				#UNKNOWN action 4. Alternate event data:0x4 0x0 0x0 0x0
				#UNKNOWN action 1. Alternate event data:0x1 0x0 0x3 0x0
				#UNKNOWN action 1. Alternate event data:0x1 0x0 0x3 0x0

				# Mario/Peach connect
				#UNKNOWN action 1. Alternate event data:0x1 0x0 0x1 0x0
				#UNKNOWN action 4. Alternate event data:0x4 0x0 0x0 0x0
				#UNKNOWN action 11. Alternate event data:0xb 0x0 0xdd 0x21
				#UNKNOWN action 1. Alternate event data:0x1 0x0 0x3 0x0

				# Mario/Peach connect
				#UNKNOWN action 1. Alternate event data:0x1 0x0 0x3 0x0
				#UNKNOWN action 4. Alternate event data:0x4 0x0 0x0 0x0
				#UNKNOWN action 11. Alternate event data:0xb 0x0 0x65 0xf5
				#UNKNOWN action 1. Alternate event data:0x1 0x0 0x1 0x0

				#UNKNOWN action 4. Alternate event data:0x4 0x0 0x0 0x0
				#UNKNOWN action 11. Alternate event data:0xb 0x0 0x3 0x8c


				return ('unknown', f'UNKNOWN action {action}. Alternate event data:'+" ".join(hex(n) for n in data))
		else:
			return ('unknown', "UNKNOWN non-mode-0-style alternate event data:"+" ".join(hex(n) for n in data))
