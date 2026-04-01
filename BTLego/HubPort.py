class HubPort():

	def __init__(self, port):
		self.port_number = port
		self.attached_device = None
		self.modes = {}
		self.mode_combinations = None
		self.mode_count = 0
		self.virtual_port_capable = False

	def attach_device(self, device):
		# FIXME: Reattachment
		self.attached_device = device

	def detach_device(self):
		self.attached_device.status = 0x0		# Decoder.io_event_type_str[0x0]

	def payload_for_port_info(port, mode_info):
		# 3.15.2
		# mode_info:
		# 0: Request port_value_single value
		# 1: Request port_info for port modes
		# 2: Request port_info for mode combinations
		mode_int = int(mode_info)
		if mode_int > 2 or mode_int < 0:
			return
		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x21,	# Command: port_info_req
			# end header
			port,
			mode_int
		])
		payload[0] = len(payload)
		return payload
