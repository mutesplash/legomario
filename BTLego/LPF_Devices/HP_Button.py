import asyncio

from .LPF_Device import LPF_Device, Devtype
from .Hub_Property import Hub_Property
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Button(Hub_Property):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.PROPERTY
		self.name = 'Button'
		self.port = Decoder.hub_property_ints[self.name]
		self.port_id = 0x0	# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]
		self.delta_interval = 0

		self.generated_message_types = (
			'event',
		)

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: (0, False)
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	def get_message(self, bt_message):
		if self.mode_subs[0][1]:
			if bt_message['value']:
				return ('event','button','pressed')
			else:
				# Well, nobody cares if it WASN'T pressed...
				pass
		return None

	def PIFSetup_data_for_message_type(self, message_type):
		if message_type == 'event':
			return True

		# FIXME: What should properties be returning here, then?

		# return 4-item array [port, mode, delta interval, subscribe on/off]
		# Base class returns nothing
		# FIXME: use abc
		return None

	def set_subscribe(self, message_type, should_subscribe):
		if message_type == 'event':
			# Ignore the delta, doesn't matter for hub properties
			self.mode_subs[0] = ( 0 , should_subscribe)
		else:
			return False
		return True