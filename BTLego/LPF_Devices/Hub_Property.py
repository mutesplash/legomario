import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Hub_Property(LPF_Device):

	# Consumer message to generate (if subscribed to property) from bluetooth message
	def get_message(self, bt_message):
		if self.mode_subs[0][1]:
			# return the message
			pass
		return None

	# Using self.port as the property identifier
	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation
		hub_property_int = self.port
		hub_property_operation = 0x3
		if should_subscribe:
			hub_property_operation = 0x2

		hub_property_update_subscription_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			hub_property_int,
			hub_property_operation
		])

		return hub_property_update_subscription_bytes
