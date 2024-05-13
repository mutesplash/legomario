import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from .LPF_BasicMotor import LPF_BasicMotor

class LPF_EncoderMotor(LPF_BasicMotor):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.LPF

		# FIXME: Can't subscribe to more than one.  Time to figure out combo modes, right?
		# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
		self.mode_subs[1] = [ self.delta_interval, False, 'SPEED', ('motor_speed',)];
		self.mode_subs[2] = [ self.delta_interval, False, 'POS', ('motor_pos',)]

	def decode_pvs(self, port, data):
		# FIXME: You're gonna want to set the deltas for POS and APOS...

		# Mode 2
		if len(data) == 4:
			# 0 to 4294967295 (MAX_INT_32) wraps around
			pos = int.from_bytes(data[0:4], byteorder="little")
			return ('motor_pos','pos',pos )

		return super().decode_pvs(port, data)
