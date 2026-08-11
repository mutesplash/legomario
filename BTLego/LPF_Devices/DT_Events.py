import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class DT_Events(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x5a
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ 1, False, 'VERS', ('duplotrain_event_ver',)],
			1: [ 1, False, 'EVENTS', ('duplotrain_events',)],	# Don't really know what this is
			2: [ self.delta_interval, False, 'DEBUG', ()]
		}

	def decode_pvs(self, port, data):
		# Mode 1
		if len(data) == 4:

			first_bytes = int.from_bytes(data[0:2], byteorder="little")
			second_bytes = int.from_bytes(data[2:], byteorder="little")

			if first_bytes == 40961:
				# Speed: 100 is zero.  IDK why, just go with the theory
				adjusted_speed = second_bytes-100
				print(f'DT Event: TRAIN SPEED {adjusted_speed}')
				return

			elif first_bytes == 1 and second_bytes == 4097:
				print(f'DT Event: EVENTS START')
				return

			else:
				print(f'DT Event: {first_bytes} | {second_bytes}')
				return

		data_dump = " ".join(hex(n) for n in data)
		print(f"DT Event: IDK {len(data)}:{data_dump}")