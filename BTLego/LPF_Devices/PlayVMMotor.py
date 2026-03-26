import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from .LPF_TachoMotor import LPF_TachoMotor

class PlayVMMotor(LPF_TachoMotor):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x56
		self.name = Decoder.io_type_id_str[self.port_id]

		# TechnicMove renamed TachoMotor's APOS for some reason
		self.mode_subs[3] = [ self.delta_interval, False, 'GOPOS', ('motor_apos',)];
		self.mode_subs[4] = [ self.delta_interval, False, 'STATS', ()]
