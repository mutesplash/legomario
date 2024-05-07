import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Color(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		self.port_id = 0x3d
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.delta_interval = 1

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'COLOR', ('color',)],
			1: [ self.delta_interval, False, 'REFLT', ('reflectivity',)],	# 0 - 100
			2: [ self.delta_interval, False, 'AMBI', ('ambient_light',)],	# 0 - 100
			3: [ self.delta_interval, False, 'LIGHT', ('light',)],
			4: [ self.delta_interval, False, 'RREFL', ()],	# 0- 1024, 2 16bit datasets with 4 total figures"
			5: [ self.delta_interval, False, 'RGB I', ('rgb_i',)],	# 0 - 1024
			6: [ self.delta_interval, False, 'HSV', ()],	# 0 -360, 3 16bit datasets with 4 total figures
			7: [ self.delta_interval, False, 'SHSV', ()],	# 0 -360, 4 16bit datasets with 4 total figures
			8: [ self.delta_interval, False, 'DEBUG', ()]	# NO IO
		}

	def decode_pvs(self, port, data):
		if port != self.port:
			return None

		if self.mode_subs[0][1]:
			color = int.from_bytes(data, byteorder="little")

			if color == 0:
				color = 'black'
			elif color == 1:
				color = 'magenta'
			elif color == 3:
				color = 'blue'
			elif color == 4:
				color = 'cyan'
			elif color == 5:
				color = 'green'
			elif color == 7:
				color = 'yellow'
			elif color == 9:
				color = 'red'
			elif color == 10:
				color = 'white'
			elif color == 255:
				color = 'none'
			else:
				# 2, 6, 8
				color = f'UNKNOWN_{color}'

			return ('color','color', color )

		elif self.mode_subs[1][1]:
			reflectivity = int.from_bytes(data, byteorder="little")
			return ('color','reflectivity', reflectivity )

		elif self.mode_subs[2][1]:
			ambient = int.from_bytes(data, byteorder="little")
			return ('color','ambient_light', ambient )

		elif self.mode_subs[5][1]:
			if len(data) == 8:
				# IDK why it goes > 255
				r = int.from_bytes(data[:2], byteorder="little")
				g = int.from_bytes(data[2:4], byteorder="little")
				b = int.from_bytes(data[4:6], byteorder="little")
				i = int.from_bytes(data[6:8], byteorder="little")
				return ('rgb_i','quad',(r, g, i, i))
		return None


	async def send_message(self, message, gatt_payload_writer):
		processed = await super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]
		payload = None
		mode = -1

		if action == 'light':
			mode = 3
			if len(parameters) != 3:
				return False

			# With the LEGO logo on the back face up, rotate the sensor to face
			# you.
			# One: Upper left LED
			# Two: Lower LED
			# Three: Upper right LED
			# Intensity levels 0 - 100

			one = int(parameters[0])
			two = int(parameters[1])
			three = int(parameters[2])

			if one > 100:
				one = 100
			if two > 100:
				two = 100
			if three > 100:
				three = 100

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Mode 3: LIGHT
				one,
				two,
				three
			])
			payload[0] = len(payload)

		if payload:
			await self.select_mode_if_not_selected(mode, gatt_payload_writer)
			await gatt_payload_writer(payload)
			return True

		return False

