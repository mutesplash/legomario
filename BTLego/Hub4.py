from .BLE_LWP_Device import BLE_LWP_Device
from .Decoder import Decoder, LDev

class Hub4(BLE_LWP_Device):

	def __init__(self, advertisement_data=None, shortname=''):
		super().__init__(advertisement_data, shortname)

		self.part_identifier = 88009

		self.minimum_attached_ports = 3

		self.mode_probe_ignored_info_types = ( 0x8, )	# Doesn't support capability bits
		# Seemingly the only hub to support motor bias

	# Override
	async def _process_bt_message(self, bt_message):

		if Decoder.message_type_str[bt_message['type']] == 'hub_attached_io':
			event = Decoder.io_event_type_str[bt_message['event']]

			if event == 'attached':
				devid = bt_message['io_type_id']
				if (
					# BUT, it will read selected mode data from it like speed, pos, apos
					devid == LDev.CONTROLPLUS_LARGE
					or devid == LDev.CONTROLPLUS_XL
					or devid == LDev.MOTOR_BOOST
					or devid == LDev.MOTOR_S
					or devid == LDev.MOTOR_M_G
					or devid == LDev.MOTOR_M_B
					or devid == LDev.MOTOR_L_G
					or devid == LDev.MOTOR_L_B
					):

					# Alright, FIXME
					# If you connect the handset to this hub, it WILL drive any motor
					# But if you set the power, nothing seems to work
					print(f"WARNING: This hub will NOT power {Decoder.io_type_id_str[devid]}... yet")

				elif devid == LDev.MATRIX:
					# It constantly reconnects to it.  Similar to how BuildHAT
					# used to work when you didn't specify full power to the
					# port.
					# https://philohome.com/motors/motorcomp.htm
					# That would explain why the above motors won't work either,
					# since they seem to use more wattage than the MOTOR_BOOST
					# that works fine
					print(f"ERROR: This hub will NOT operate {Decoder.io_type_id_str[devid]} properly!")

				elif (
					devid == LDev.COLOR
					or devid == LDev.ULTRA
					):
					# Ignores commands to power the lights on the devices
					print(f"ERROR: This hub will NOT operate {Decoder.io_type_id_str[devid]} properly!")


		return await super()._process_bt_message(bt_message)
