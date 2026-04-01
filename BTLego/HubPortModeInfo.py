from .Decoder import Decoder

class HubPortModeInfo():

	def __init__(self, port):
		self.probe_state = None

# 		def scan_mode(direction, port, mode):
# 			if not mode in self.port_mode_info[port]:
# 				self.port_mode_info[port][mode] = {
# 					'requests_outstanding':{
# 						0x0:True,	# NAME
# 						0x1:True,	# RAW
# 						0x2:True,	# PCT
# 						0x3:True,	# SI
# 						0x4:True,	# SYMBOL
# 						0x5:True,	# MAPPING
# 						0x7:True,	# Mario throws 'Invalid use of command' if it doesn't support motor bias, any other BLE Lego things support it?
# 						0x8:True,	# Mario doesn't seem to support Capability bits
# 						0x80:True	# VALUE FORMAT
# 					},
# 					'direction':direction
# 				}
#
# 				for mode_info_type_number in self.mode_probe_ignored_info_types:
# 					del self.port_mode_info[port][mode]['requests_outstanding'][mode_info_type_number]
#
# 				# If the BLE_Device supports motor bias, only enable on approved LPF devices
# 				if 0x7 in self.port_mode_info[port][mode]['requests_outstanding']:
# 					if not device.port_id in LPF_Device.motor_bias_device_allowlist:
# 						del self.port_mode_info[port][mode]['requests_outstanding'][0x7]
#
# 			frozen_requests = list(self.port_mode_info[port][mode]['requests_outstanding'].items())
# 			for hexkey, requested in frozen_requests:
# 				if requested:
# 					self._write_port_mode_info_request(port,mode,hexkey)

	def generate_info_requests():
		pass
		# see _decode_mode_info_and_interrogate

	def parse_info_requests():
		pass
		# see _decode_port_mode_info()

	def payload_for_port_mode_info_request(port, mode, infotype):
		if mode < 0 or mode > 255:
			self.logger.error('Invalid mode '+str(mode)+' for mode info request')
			return None
		if not infotype in Decoder.mode_info_type_str:
			self.logger.error('Invalid information type '+hex(infotype)+' for mode info request')
			return None

		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x22,	# Command: port_mode_info_req
			# end header
			port,
			mode,
			infotype	# 0-8 & 0x80
		])
		payload[0] = len(payload)

# FIXME: Check for range issues with bluetooth  on write_gatt_char (device goes too far away)
#    raise BleakError("Characteristic {} was not found!".format(char_specifier))
#bleak.exc.BleakError: Characteristic 00001624-1212-efde-1623-785feabcd123 was not found!

# or it just disappears
# AttributeError: 'NoneType' object has no attribute 'write_gatt_char'
		return payload
