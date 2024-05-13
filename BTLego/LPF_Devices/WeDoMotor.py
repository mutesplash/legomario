import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from .LPF_BasicMotor import LPF_BasicMotor

class WeDoMotor(LPF_BasicMotor):

	def __init__(self, port=-1):
		super().__init__(port)

		self.part_identifier = 45303

		self.port_id = 0x1
		self.name = Decoder.io_type_id_str[self.port_id]

		# Basic motor, but it names mode 0 differently because I guess differentiating
		# on the port id isn't enough
		self.mode_subs[0] = [ self.delta_interval, False, 'LPF2-MMOTOR', ()]	# Not subscribe-able
