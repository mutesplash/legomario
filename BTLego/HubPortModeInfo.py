from .Decoder import Decoder
import logging

class HubPortModeInfo():

	# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]

	def __init__(self, port, mode):

		self.logger = logging.getLogger(__name__.split('.')[0])

		self.mode_number = mode
		self.mode_direction = None
		self.port = port
		self.mode_requests = {}

		self.name = None
		self.raw_min = None
		self.raw_max = None
		self.pct_min = None
		self.pct_max = None
		self.si_min = None
		self.si_max = None
		self.symbol = None
		self.mapping = {}
		self.motor_bias = None
		self.capability_readable = None # FIXME
		self.value_readable = None

	def dump_info(self):
		retval = {}
		retval['mode'] = self.mode_number
		retval['direction'] = self.mode_direction
		retval['name'] = self.name
		retval['raw'] = {
			"min": self.raw_min,
			"max": self.raw_max
		}
		retval['pct'] = {
			"min": self.pct_min,
			"max": self.pct_max
		}
		retval['si'] = {
			"min": self.si_min,
			"max": self.si_max
		}
		retval['symbol'] = self.symbol
		retval['mapping'] = self.mapping
		retval['capability_readable'] = self.capability_readable
		retval['value_readable'] = self.value_readable
		return retval

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

	def process_mode_info_request(self, bt_message):

		mode_info_hexkey = bt_message['mode_info_type']

		if not mode_info_hexkey in self.mode_requests:
			self.logger.warning(f"EXTRA mode info type {hex(bt_message['mode_info_type'])} on port {port} mode {mode} DUMP:{bt_message['readable']}")
			return

		if self.mode_requests[mode_info_hexkey] == False:
			self.logger.warning(f'WARN: Did not expect this mode info report, refusing to update: {bt_message["readable"]}')
			return

		if bt_message['port'] != self.port:
			self.logger.error(f'ERROR: Message routed to incorrect port {self.port}, mode {self.mode}: {bt_message["readable"]}')
			return
		if bt_message['mode'] != self.mode_number:
			self.logger.error(f'ERROR: Message routed to incorrect mode {self.mode} on port {self.port}: {bt_message["readable"]}')
			return

		readable = bt_message['readable']

		if mode_info_hexkey in Decoder.mode_info_type_str:
			readable += ' '+Decoder.mode_info_type_str[mode_info_hexkey]+':'
		else:
			readable += ' infotype_'+str(mode_info_hexkey)+':'

		# Name
		decoded = True
		if mode_info_hexkey == 0x0:
			# readable += bt_message['name']
			self.name = bt_message['name']
		# Raw
		elif mode_info_hexkey == 0x1:
			#readable += ' Min: '+str(bt_message['raw']['min'])+' Max: '+str(bt_message['raw']['max'])
			self.raw_min = bt_message['raw']['min']
			self.raw_max = bt_message['raw']['max']
		# Percentage range window scale
		elif mode_info_hexkey == 0x2:
			#readable += ' Min: '+str(bt_message['pct']['min'])+' Max: '+str(bt_message['pct']['max'])
			self.pct_min = bt_message['pct']['min']
			self.pct_max = bt_message['pct']['max']
		# SI Range
		elif mode_info_hexkey == 0x3:
			#readable += ' Min: '+str(bt_message['si']['min'])+' Max: '+str(bt_message['si']['max'])
			self.si_min = bt_message['si']['min']
			self.si_max = bt_message['si']['max']
		# Symbol
		elif mode_info_hexkey == 0x4:
			#readable += bt_message['symbol']
			self.symbol = bt_message['symbol']

		# Mapping
		elif mode_info_hexkey == 0x5:
			#self.port_mode_info[port][mode]['mapping_readable'] = bt_message['readable']

			if bt_message['IN_mapping']:
				self.mapping['input_mappable'] = bt_message['IN_maptype']
			else:
				if bt_message['IN_maptype']:
					self.mapping['not_input_mappable'] = bt_message['IN_maptype']

			if bt_message['OUT_mapping']:
				self.mapping['output_mappable'] = bt_message['OUT_maptype']
			else:
				if bt_message['OUT_maptype']:
					self.mapping['not_output_mappable'] = bt_message['OUT_maptype']

			if bt_message['IN_nullable']:
				self.mapping['input_nullable'] = True
			if bt_message['OUT_nullable']:
				self.mapping['output_nullable'] = True

		elif mode_info_hexkey == 0x7:
			#readable += ' Motor bias: '+bt_message['motor_bias']
			self.motor_bias = bt_message['motor_bias']

		elif mode_info_hexkey == 0x8:
			# Capability bits
			# FIXME
			#readable += bt_message['readable']
			self.capability_readable = bt_message['readable']

		# Value format
		elif mode_info_hexkey == 0x80:
			readable = ''
			readable += ' '+str(bt_message['datasets']) + ' '+ bt_message['dataset_type']+ ' datasets'
			readable += ' with '+str(bt_message['total_figures'])+' total figures and '+str(bt_message['decimals'])+' decimals'

			self.value_readable = readable
		else:
			readable = f"IDK_DEVICE port {self.port}, mode {self.mode_number}: INFO TYPE: {hex(mode_info_hexkey)}"
			decoded = False

		if not decoded:
			self.logger.warning(f'WARN: No PMI decoder for this: {readable}')
		else:
			self.logger.debug(f'PMI Decoded: {readable}')
			self.mode_requests.pop(mode_info_hexkey,None)
			if not self.mode_requests:
				self.logger.debug(f"COMPLETE: Probe for mode {self.mode_number} on port {self.port}")

	def mode_info_requests_outstanding(self):
		outstanding_requests = 0
		for mode_info_hexkey in self.mode_requests:
			if self.mode_requests[mode_info_hexkey] == True:
				outstanding_requests += 1
		return outstanding_requests

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
