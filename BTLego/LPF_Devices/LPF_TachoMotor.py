import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from .LPF_EncoderMotor import LPF_EncoderMotor

class LPF_TachoMotor(LPF_EncoderMotor):

	def __init__(self, port=-1):
		super().__init__(port)

		self.mode_subs[3] = [ self.delta_interval, False, 'APOS', ('motor_apos',)]

	def decode_pvs(self, port, data):
		# FIXME: You're gonna want to set the deltas for POS and APOS...

		# Mode 3
		if len(data) == 2:
			# -180 to 179
			apos = int.from_bytes(data[0:2], byteorder="little", signed=True)
			return ('motor_apos','apos',apos )

		return super().decode_pvs(port, data)
