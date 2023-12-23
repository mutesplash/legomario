import asyncio

from .LPF_Device import LPF_Device, Devtype
from .Hub_Property import Hub_Property
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class MarioVolume(Hub_Property):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device
		self.devtype = Devtype.PROPERTY
		self.name = 'Mario Volume'
		self.port = Decoder.hub_property_ints[self.name]
		self.port_id = 0x0	# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]
		self.delta_interval = 0

		self.volume = 100	# Defaults to max

		self.generated_message_types = (
			'info',
		)

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: (0, False)
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def get_message(self, bt_message):

		if Decoder.message_type_str[bt_message['type']] == 'hub_properties':
			if Decoder.hub_property_op_str[bt_message['operation']] == 'Update':
				if bt_message['property'] in Decoder.hub_property_str:
					# hat tip to https://github.com/djipko/legomario.py/blob/master/legomario.py
					if Decoder.hub_property_str[bt_message['property']] == 'Mario Volume':
						if self.mode_subs[0][1]:
#							print("(HP_MarioVolume) Volume set to "+str(bt_message['value']))

							self.volume = bt_message['value']

							return ('info','volume',bt_message['value'])

		return None

	def PIFSetup_data_for_message_type(self, message_type):
		if message_type == 'info':
			return True

		# FIXME: What should properties be returning here, then?

		# return 4-item array [port, mode, delta interval, subscribe on/off]
		# Base class returns nothing
		# FIXME: use abc
		return None

	def set_subscribe(self, message_type, should_subscribe):
		if message_type == 'info':
			# Ignore the delta, doesn't matter for hub properties
			self.mode_subs[0] = ( 0 , should_subscribe)
		else:
			return False
		return True


	def send_message(self, message):
		# ( action, (parameters,) )
		action = message[0]
		parameters = message[1]

		if action == 'set_volume':
			volume = parameters[0]
			if volume > 100 or volume < 0:
				return None
			# The levels in the app are 100, 90, 75, 50, 0
			# Which is weird, but whatever
			set_volume_bytes = bytearray([
				0x06,	# len placeholder
				0x00,	# padding but maybe stuff in the future (:
				0x1,	# 'hub_properties'
				0x12,	# 'Mario Volume'
				0x1,	# 'Set'
				volume
			])

			self.volume = volume
			set_volume_bytes[0] = len(set_volume_bytes)

			ret_message = { 'gatt_send': (set_volume_bytes,) }
			return ret_message

		elif action == 'get_volume':
			# Triggers hub_properties message
			property_update_bytes = bytearray([
				0x05,	# len
				0x00,	# padding but maybe stuff in the future (:
				0x1,	# 'hub_properties'
				self.port,	# 'Mario Volume'
				0x5		# 'Request Update'
			])

			property_update_bytes[0] = len(property_update_bytes)
			ret_message = { 'gatt_send': (property_update_bytes,) }
			return ret_message

		return None

