from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class SixLED(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x58
		self.name = Decoder.io_type_id_str[self.port_id]

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, '6LEDS', ()]
		}

	def send_message(self, message, gatt_payload_writer):
		processed = super().send_message(message, gatt_payload_writer)
		if processed:
			return processed
		# ( action, (parameters,) )

		action = message[0]
		parameters = message[1]


		if action == 'set_6led':
			led_select = int(parameters[0])
			led_power = int(parameters[1])

			# FIXME: Bad naming and positioning
			#	Front: 1, 2, 3, 4 (head on)
			#	Back:  6, 5 (head on)

			if led_select > 6 or led_select < 1:
				return False

			# Can't do multiple LEDs at the same time despite it seemingly being a bitfield
			# FIXME: Bit shift this instead
			led_bitselect = 0
			if led_select == 1:
				led_bitselect = 1
			elif led_select == 2:
				led_bitselect = 2
			elif led_select == 3:
				led_bitselect = 4
			elif led_select == 4:
				led_bitselect = 8
			elif led_select == 5:
				led_bitselect = 16
			elif led_select == 6:
				led_bitselect = 32

			mode = 0

			payload = bytearray([
				0x7,	# len
				0x0,	# padding
				0x81,	# Command: port_output_command
				# end header
				self.port,
				0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
				0x51,	# Subcommand: WriteDirectModeData
				mode,	# Appendix 6.1
				led_bitselect,
				led_power
			])
			payload[0] = len(payload)
			gatt_payload_writer(payload, 'port_writes')
			return True

		return False
