import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Force(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		self.port_id = 0x3f
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'FORCE', ('force', )],
			1: [ 1, False, 'TOUCH', ('touch',)],					# Binary yes/no so delta must be 1
			2: [ 1, False, 'TAP', ( 'tap', )],						# Won't pick up with a delta of 5 because it's measured in seconds and the max is 3
			3: [ self.delta_interval, False, 'FPEAK', ('peak',)],	# Peak requires the sensor to be unplugged to forget
			4: [ self.delta_interval, False, 'FRAW', ('force_raw',)],
			5: [ self.delta_interval, False, 'FPRAW', ('peak_raw',)],
			6: [ -1, False, 'CALIB', ()]	# NO IO
		}

	def decode_pvs(self, port, data):
		if port != self.port:
			return None

		mode = self._selected_mode

		if not self.outstanding_requests.empty():
			mode = self.outstanding_requests.get()

		if mode == 0:
			if len(data) == 1:
				return ('force','percentage', int.from_bytes(data, byteorder="little") )

		if mode == 1:
			if len(data) == 1:
				# 0 or 1.  Button is touched (in force sensing range or not) or is not
				return ('force','touch', int.from_bytes(data, byteorder="little") )

		if mode == 2:
			if len(data) == 1:
				# 0 to 3
				# Maximum seconds for tap detection is 3 and then reports zero,
				# and waits until zeroed before reporting again
				return ('force','tap_seconds', int.from_bytes(data, byteorder="little") )

		if mode == 3:
			if len(data) == 1:
				return ('force','peak_percentage', int.from_bytes(data, byteorder="little") )

		if mode == 4:
			if len(data) == 2:
				# Max seen is 701
				return ('force','force_raw', int.from_bytes(data, byteorder="little") )

		if mode == 5:
			if len(data) == 2:
				# Max seen is 701
				return ('force','peak_raw', int.from_bytes(data, byteorder="little") )

		return None

	async def send_message(self, message, gatt_payload_writer):
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]

		if action == 'get_tap':
			mode = 2
			return await self.get_port_info(mode, gatt_payload_writer)

		elif action == 'get_peak':
			mode = 3
			return await self.get_port_info(mode, gatt_payload_writer)

		return False
