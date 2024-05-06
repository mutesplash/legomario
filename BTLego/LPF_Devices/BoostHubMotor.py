import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from .LPF_EncoderMotor import LPF_EncoderMotor

class BoostHubMotor(LPF_EncoderMotor):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x27
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# The speeds on motor A / Port 0 are backwards.  I guess this is so
		# you send the SAME command to BOTH ports and they do what you expect
		# which is move the entire hub in the same direction.

		# With "forward" being the side that the green button is on:
		# Clockwise on motor A / port 0 is "move hub backward" and activated with
		# negative speed
		# Clockwise on motor B / port 1 is "move hub forward" and activated with
		# positive speed, same for every other motor.

		# FIXME: After decoding the tilt sensor, it's clear that you "lead with the LED"
		# and that direction is forwards.  Internet confirms this so fix above
		# text

