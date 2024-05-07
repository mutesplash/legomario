import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class PUH_IMU_Accel(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x39
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.delta_interval = 2

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'GRV', ('puh_acceleration',) ],
			1: [ self.delta_interval, False, 'CAL', ()]
		}

	def decode_pvs(self, port, data):
		if port != self.port:
			print('Bad port')
			return None

		if len(data) == 6:

			# Port reports unit as "mG"
			# milli... 9.8m/s^2? 32ft/s^2? Galileo?
			# Either way, can't really figure out what the numbers actually mean

			# one: Axis is the line perpendicular to the plane that entirely contains two and three
			#	~4180 when tipped to LED pointing up (-4100 pointed down)
			# two: Axis is the line perpendicular to the plane splitting the LED and Button
			#	~4080 when ports D & B pointing up (-4140 with A & C pointing up)
			# three: Axis is the line perpendicular to the plane of the case split
			#	~4140 when battery pack flat on table (-4110 upside down)

			one = int.from_bytes(data[0:2], byteorder="little", signed=True)
			two = int.from_bytes(data[2:4], byteorder="little", signed=True)
			three = int.from_bytes(data[4:], byteorder="little", signed=True)

			return ('imu', 'accel', (one, two, three) )

		else:
			print('UNKNOWN IMU ACCEL DATA '+' '.join(hex(n) for n in data))
			return None
