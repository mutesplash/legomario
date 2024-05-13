import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from .LPF_TachoMotor import LPF_TachoMotor

class AngularMediumAzure(LPF_TachoMotor):

	def __init__(self, port=-1):
		super().__init__(port)

		self.part_identifier = 45603

		self.port_id = 0x30
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# Hey, look it _IS_ different from the Grey one!
		self.mode_subs[4] = [ self.delta_interval, False, 'LOAD', ('motor_load',)]
		self.mode_subs[5] = [ self.delta_interval, False, 'CALIB', ()]	# NO IO
