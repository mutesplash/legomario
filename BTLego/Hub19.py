from .BLE_LWP_Device import BLE_LWP_Device

class Hub19(BLE_LWP_Device):

	def __init__(self,advertisement_data=None, json_code_dict=None):
		super().__init__(advertisement_data)

		self.part_identifier = '103479c01'

		self.minimum_attached_ports = 15

		self.mode_probe_ignored_info_types = ( 0x7, )	# Doesn't support motor bias ??
