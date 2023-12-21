import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Controller_Buttons(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.FIXED

		# Side A is left, port 0
		# Side B is right, port 1
		self.port = port

		self.port_id = 0x37
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.generated_message_types = (
			'controller_buttons',
		)

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			1: ( 0, False)	# Value other than zero doesn't really work for the buttons
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def set_subscribe(self, message_type, should_subscribe):
		if message_type == 'controller_buttons':
			mode_for_message_type = 1
			# Don't change the delta
			self.mode_subs[mode_for_message_type] = (self.mode_subs[mode_for_message_type][0], should_subscribe)
		else:
			return False
		return True

	def PIFSetup_data_for_message_type(self, message_type):
		# return 4-item array [port, mode, delta interval, subscribe on/off]
		# Base class returns nothing
		# FIXME: use abc

		if message_type == 'controller_buttons':
			single_mode = 1
			return (self.port, single_mode, *self.mode_subs[single_mode], )

		return None

	# After getting the Value Format out of the controller, that allowed me to find this page
	# https://virantha.github.io/bricknil/lego_api/lego.html#remote-buttons
	def decode_pvs(self, port, data):
		if len(data) != 1:
			# PORT 1: handset UNKNOWN BUTTON DATA, WEIRD LENGTH OF 3:0x0 0x0 0x0
			return None

		side = 'left'		# A side
		if port == 1:
			side = 'right'	# B side

		button_id = data[0]
		if button_id == 0x0:
			return ('controller_buttons',side,'zero')
		elif button_id == 0x1:
			return ('controller_buttons',side,'plus')
		elif button_id == 0x7f:
			return ('controller_buttons',side,'center')
		elif button_id == 0xff:
			return ('controller_buttons',side,'minus')

		return None

	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation

		# Port Input Format Setup (Single) message
		# Sending this results in port_input_format_single response

		payload = bytearray()
		if message_type == 'controller_buttons':
			mode = 1
			payload.extend([
				0x0A,		# length
				0x00,
				0x41,		# Port input format (single)
				self.port,	# port
				1,			# mode for controller_buttons
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