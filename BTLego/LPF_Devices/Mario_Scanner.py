import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from ..MarioScanspace import MarioScanspace

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Mario_Scanner(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.FIXED

		self.port = port

		self.port_id = 0x49
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.generated_message_types = (
			'scanner',
		)

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 5, False),		# TAG (default?)
			1: ( 5, False)		# RGB
			# FIXME: So, I've slept since I did this.  Some of these things just transmit by default, how does the subscribe_boolean reflect this?
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def decode_pvs(self, port, data):
		# RGB Mode 0
		if len(data) != 4:
			print("(Mario_Scanner) UNKNOWN SCANNER DATA, WEIRD LENGTH OF "+len(data)+":"+" ".join(hex(n) for n in data))
			return ( None, )

		scantype = None
		if data[2] == 0xff and data[3] == 0xff:
			scantype = 'barcode'
		if data[0] == 0xff and data[1] == 0xff:
			if scantype == 'barcode':
				scantype = 'nothing'
			else:
				scantype = 'color'

		if not scantype:
			print ("(Mario_Scanner) UNKNOWN SCANNER DATA:"+" ".join(hex(n) for n in data))
			return ( None, )

		if scantype == 'barcode':
			barcode_int = int.from_bytes(data[0:2], byteorder="little")
			# Max 16-bit signed int, Github Issue #4
			if barcode_int != 32767:
				# Happens when Black is used as a color
				code_info = MarioScanspace.get_code_info(barcode_int)
				print("(Mario_Scanner) scanned "+code_info['label']+" (" + code_info['barcode']+ " "+str(barcode_int)+")")
				return ('scanner','code',(code_info['barcode'], barcode_int))
			else:
				# FIXME: Scanner, error, instead?
				return ('error','message','Scanned malformed code')
		elif scantype == 'color':
			color = MarioScanspace.mario_bytes_to_solid_color(data[2:4])
			print("(Mario_Scanner) scanned color "+color)
			return ('scanner','color',color)
		else:
			#scantype == 'nothing':
			print("(Mario_Scanner) scanned nothing")
			return ( None, )


	def set_subscribe(self, message_type, should_subscribe):
		if message_type == 'scanner':
			mode_for_message_type = 0
			# Don't change the delta
			self.mode_subs[mode_for_message_type] = (self.mode_subs[mode_for_message_type][0], should_subscribe)
		else:
			return False
		return True

	def PIFSetup_data_for_message_type(self, message_type):
		# return 4-item array [port, mode, delta interval, subscribe on/off]
		# Base class returns nothing
		# FIXME: use abc

		if message_type == 'scanner':
			single_mode = 0
			return (self.port, single_mode, *self.mode_subs[single_mode], )

		return None

	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation

		# Port Input Format Setup (Single) message
		# Sending this results in port_input_format_single response

		payload = bytearray()
		if message_type == 'scanner':
			mode = 0		# mode for scanner
			payload.extend([
				0x0A,		# length
				0x00,
				0x41,		# Port input format (single)
				self.port,	# port
				mode,
			])

			# delta interval (uint32)
			# 5 is what was suggested by https://github.com/salendron/pyLegoMario
			# 88010 Controller buttons for +/- DO NOT WORK without a delta of zero.
			# Amusingly, this is strongly _not_ recommended by the LEGO docs
			# Kind of makes sense, though, since they are discrete (and debounced, I assume)
			delta_int = self.mode_subs[mode][0]
			payload.extend(delta_int.to_bytes(4,byteorder='little',signed=False))

			if should_subscribe:
				payload.append(0x1)		# notification enable
			else:
				payload.append(0x0)		# notification disable
			#print(" ".join(hex(n) for n in payload))

		return payload
