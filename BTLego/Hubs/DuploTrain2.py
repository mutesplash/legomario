import asyncio

from .BLE_LWP_Device import BLE_LWP_Device
from ..Decoder import Decoder

class DuploTrain2(BLE_LWP_Device):

	def __init__(self, advertisement_data=None, shortname=''):
		super().__init__(advertisement_data, shortname)

		self.part_identifier = "103651c01"

		self.minimum_attached_ports = 5




