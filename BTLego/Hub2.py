from .BLE_Device import BLE_Device

class Hub2(BLE_Device):

	def __init__(self,advertisement_data=None, json_code_dict=None):
		super().__init__(advertisement_data)

		self.part_identifier = 88012

		self.mode_probe_ignored_info_types = ( 0x7, 0x8 )	# Doesn't support motor bias or capability bits
