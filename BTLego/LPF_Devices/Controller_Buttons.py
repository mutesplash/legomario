import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Controller_Buttons(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.FIXED

		# Well, let's hope they don't put this device on anything else...
		# Side A is left, port 0
		# Side B is right, port 1
		self.port = port

		self.port_id = 0x37
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# 88010 Controller buttons in Mode 1 for +/- DO NOT WORK without a delta
		# interval of zero.
		# Amusingly, this is strongly _not_ recommended by the LEGO docs
		# Kind of makes sense, though, since they are discrete (and debounced, I assume)
		self.delta_interval = 0

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'RCKEY', ()],
			1: [ self.delta_interval, False, 'KEYA', ('controller_buttons',)],
			2: [ self.delta_interval, False, 'KEYR', ()],
			3: [ self.delta_interval, False, 'KEYD', ()],
			2: [ self.delta_interval, False, 'KEYSD', ()]
		}

	# After getting the Value Format out of the controller, that allowed me to find this page
	# https://virantha.github.io/bricknil/lego_api/lego.html#remote-buttons
	def decode_pvs(self, port, data):
		if port != self.port:
			return None

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
