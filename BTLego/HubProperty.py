from .Decoder import Decoder

class HubProperty():

	def __init__(self, ref):
		self.reference_number = ref
		self.name = Decoder.hub_property_str[ref]
		self.subscribed = False

	def gatt_payload_for_subscribe(self, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation
		hub_property_operation = 0x3
		if should_subscribe:
			hub_property_operation = 0x2

		hub_property_update_subscription_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			self.reference_number,
			hub_property_operation
		])

		return hub_property_update_subscription_bytes

	# Technically this is "request update" that language makes no sense to anyone
	def gatt_payload_for_property_value_fetch(self):
		hub_property_value_fetch_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			self.reference_number,
			0x5		# 'Request Update'
		])

		return hub_property_value_fetch_bytes

	def gatt_payload_for_property_set(self, value):
		hub_property_value_set_bytes = bytearray([
			0x06,	# len placeholder
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			self.reference_number,
			0x1,	# 'Set'

			# FIXME: Ok, is it a feature or a bug that you could literally stuff anything in here?
			value
		])
		hub_property_value_set_bytes[0] = len(hub_property_value_set_bytes)
		return hub_property_value_set_bytes