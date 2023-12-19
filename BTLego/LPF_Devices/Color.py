import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Color(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.LPF

		self.port = port

		self.port_id = 0x3d
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.generated_message_types = (
			'rgb_i',
		)

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 5, False),		# COLOR
			1: ( 5, False),		# REFLT
			2: ( 5, False),		# AMBI
			3: ( 5, False),		# LIGHT
			4: ( 5, False),		# RREFL
			5: ( 5, False),		# RGB I
			6: ( 5, False),		# HSV
			7: ( 5, False),		# SHSV
			8: ( 5, False),		# DEBUG
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def decode_pvs(self, port, data):
		if port != port:
			return None

		if len(data) == 8:
			# IDK why it goes > 255
			r = int.from_bytes(data[:2], byteorder="little")
			g = int.from_bytes(data[2:4], byteorder="little")
			b = int.from_bytes(data[4:6], byteorder="little")
			i = int.from_bytes(data[6:8], byteorder="little")
			return ('rgb_i','quad',(r, g, i, i))
		return None

	def set_subscribe(self, message_type, should_subscribe):

		mode_for_message_type = -1
		if message_type == 'rgb_i':
			mode_for_message_type = 5

		if mode_for_message_type > -1:
			self.mode_subs[mode_for_message_type] = (self.mode_subs[mode_for_message_type][0], should_subscribe)
			return True

		return False

	def PIFSetup_data_for_message_type(self, message_type):
		# return 4-item array [port, mode, delta interval, subscribe on/off]
		# Base class returns nothing
		# FIXME: use abc

		mode = -1
		if message_type == 'rgb_i':
			mode = 5
		else:
			return None

		return (self.port, mode, *self.mode_subs[mode], )

	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation

		# Port Input Format Setup (Single) message
		# Sending this results in port_input_format_single response

		mode = -1
		if message_type == 'rgb_i':
			mode = 5

		payload = bytearray()
		if mode > -1:
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