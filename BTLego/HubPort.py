from .HubPortReported import HubPortReported
from .HubPortModeInfo import HubPortModeInfo
import logging

class HubPort():

	def __init__(self, port):

		self.logger = logging.getLogger(__name__.split('.')[0])

		self.port_number = port
		self.attached_device = None
		self.parent = {}
		self.mode_probe_ignored_info_types = ()

		self.mode_probes_running = False
		self.reported = HubPortReported()	# Stuff set by PMI

	def set_parent_info(self, class_name, system_type):
		self.parent['hub_driver'] = class_name
		self.parent['type'] = system_type

	def attach_device(self, device):
		# FIXME: Reattachment
		self.attached_device = device
		if device.port != self.port_number:
			print(f"CONSISTENCY ERROR: ATTACHED DEVICE IS PORT {device.port} AND HUB PORT IS {self.port_number}")

	def detach_device(self):
		self.attached_device.status = 0x0		# Decoder.io_event_type_str[0x0]

	def dump_info(self):
		retval = {}
		if self.mode_probes_running:
			retval['probe_status'] = self.mode_probe_count()
		retval['parent'] = self.parent
		retval['parent']['attached_port'] = self.port_number
		if self.attached_device:
			retval['name'] = self.attached_device.name
			retval['port_driver'] = self.attached_device.__class__.__name__
			retval['port_id'] = self.attached_device.port_id
			retval['hw'] = self.attached_device.hw_ver_str
			retval['fw'] = self.attached_device.fw_ver_str
		else:
			retval['device_detached'] = True
		retval['virtual_port_capable']= self.reported.virtual_port_capable
		if self.reported.mode_combinations:
			retval['mode_combinations'] = self.reported.mode_combinations
		retval['mode_count'] = self.reported.mode_count
		retval['modes'] = {}
		for mode in self.reported.modes:
			retval['modes'][mode] = self.reported.modes[mode].dump_info()
		return retval

	def request_port_info(self, gatt_payload_writer):
		gatt_payload_writer(HubPort.payload_for_port_info(self.port_number, 0x1), 'port_config')
		self.mode_probes_running = True

	def check_probe_completion(self):
		if self.mode_probe_count() == 0:
			self.mode_probes_running = False
			return True
		return False

	def mode_probe_count(self):
		probes_outstanding = 0

		for mode in self.reported.modes:
			this_mode_probe_count = self.reported.modes[mode].mode_info_requests_outstanding()
			if this_mode_probe_count:
				probes_outstanding += this_mode_probe_count
		return probes_outstanding

	def reset_mode_info(self):
		self.mode_probes_running = False
		self.reported.reset_reported_info()

	# bt_message is a port_info_req response
	# 'IN': Receive data from device
	# 'OUT': Send data to device
	# Uses gatt_payload_writer to issue requests for port mode info
	def process_port_info_message(self, bt_message, gatt_payload_writer):

		port = bt_message['port']
		if port != self.port_number:
			self.logger.error(f'ERROR:Message for port {port} routed to {self.port_number}: {bt_message["readable"]}')
			return

		if not 'num_modes' in bt_message:
			if 'mode_combinations' in bt_message:
				self.reported.mode_combinations = bt_message['mode_combinations']
			else:
				self.logger.error(f'Mode combinations NOT DECODED: {bt_message["readable"]}')
			return
		else:
			self.logger.debug(f"Interrogating mode info for {bt_message['num_modes']} modes on port {port}: {self.attached_device.name}")

		if not self.mode_probes_running:
			self.logger.warning(f'WARN: Did not expect this mode info description, refusing to update: {bt_message["readable"]}')
			return

		self.reported.mode_count = bt_message['num_modes']

		# Does not note the entire bt_message['port_mode_capabilities']
		# Mostly because i/o is redundant
		# IE: {'output': True, 'input': True, 'logic_combineable': True, 'logic_synchronizeable': False}

		if bt_message['port_mode_capabilities']['logic_synchronizeable']:
			self.reported.virtual_port_capable = True

		if bt_message['port_mode_capabilities']['logic_combineable']:
			# This is a signal to check for combinations (3.15.2)
			self.logger.debug(f'\tRequest port {port} combinations...')
			gatt_payload_writer(HubPort.payload_for_port_info(port, 0x2),'port_config')

		def scan_mode(direction, port, mode):
			if not mode in self.reported.modes:
				self.reported.modes[mode] = HubPortModeInfo(port, mode)

				self.reported.modes[mode].mode_requests = {
					0x0:True,	# NAME
					0x1:True,	# RAW
					0x2:True,	# PCT
					0x3:True,	# SI
					0x4:True,	# SYMBOL
					0x5:True,	# MAPPING
					0x7:True,	# Mario throws 'Invalid use of command' if it doesn't support motor bias, any other BLE Lego things support it?
					0x8:True,	# Mario doesn't seem to support Capability bits
					0x80:True	# VALUE FORMAT
				}

				for mode_info_type_number in self.mode_probe_ignored_info_types:
					del self.reported.modes[mode].mode_requests[mode_info_type_number]

				# If the BLE_Device supports motor bias, only enable on approved LPF devices
				if 0x7 in self.reported.modes[mode].mode_requests:
					if not self.attached_device.port_id in LPF_Device.motor_bias_device_allowlist:
						del self.reported.modes[mode].mode_requests[mode_info_type_number][0x7]

			# Update direction (IN => IN/OUT or none => OUT)
			self.reported.modes[mode].mode_direction = direction

			# Probe all unprobed mode info hex key in HubPortModeInfo.mode_requests
			frozen_requests = list(self.reported.modes[mode].mode_requests.items())
			for hexkey, requested in frozen_requests:
				if requested:
#					print(f'Mode info request for port {port} / {mode} / {hexkey} / {direction}')
					gatt_payload_writer(HubPortModeInfo.payload_for_port_mode_info_request(port,mode,hexkey), 'port_config')

		bit_value = 1
		mode_number = 0
		while mode_number < 16: # or bit_value <= 32768
			if bt_message['input_bitfield'] & bit_value:
				scan_mode('IN',port,mode_number)
			bit_value <<=1
			mode_number += 1

		bit_value = 1
		mode_number = 0
		while mode_number < 16: # or bit_value <= 32768
			if bt_message['output_bitfield'] & bit_value:
				if mode_number in self.reported.modes:
					# Already scanned during the IN loop
					self.reported.modes[mode_number].mode_direction = 'IN/OUT'
				else:
					# Can't really tell the difference between in and out info request
					scan_mode('OUT',port,mode_number)
			else:
				# Note that mode_count is sent in the port info request so this
				# mode is in-range, _but_ not OUT or IN/OUT
				if mode_number + 1 <= self.reported.mode_count:
					# Also not IN, because it would have already been created by scan_mode(IN....)
					if not mode_number in self.reported.modes:
						# As seen on the Vision sensor, mode 8
						# Scan a NO-IO port?  Well, it hasn't crashed anything yet...
						scan_mode('NO-IO',port,mode_number)

			bit_value <<=1
			mode_number += 1


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
