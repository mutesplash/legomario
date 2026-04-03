from .BLE_LWP_Device import BLE_LWP_Device

class Hub2(BLE_LWP_Device):

	def __init__(self, advertisement_data=None, shortname=''):
		super().__init__(advertisement_data, shortname)

		self.part_identifier = 88012

		self.minimum_attached_ports = 9

		self.mode_probe_ignored_info_types = ( 0x7, 0x8 )	# Doesn't support motor bias or capability bits
