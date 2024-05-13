import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from .LPF_EncoderMotor import LPF_EncoderMotor

class BoostMotor(LPF_EncoderMotor):

	def __init__(self, port=-1):
		super().__init__(port)

		self.part_identifier = 88008

		self.port_id = 0x26
		self.name = Decoder.io_type_id_str[self.port_id]
