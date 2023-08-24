import asyncio
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder

class Controller(BLE_Device):
	# 0:	Don't debug
	# 1:	Print weird stuff
	# 2:	Print most of the information flow
	# 3:	Print stuff even you the debugger probably don't need
	DEBUG = 0

	message_types = (
		'controller_buttons',
		'controller_rgb',
		'controller_volts',
		'controller_RSSI',
		'connection_request'
	)

	RGB_LIGHT_PORT = 52
	CONTROLLER_VOLTS_PORT = 59
	BUTTONS_LEFT_PORT = 0
	BUTTONS_RIGHT_PORT = 1
	CONTROLLER_RSSI_PORT = 60

	# True if subscription is valid, false otherwise
	async def set_subscription(self, subscription, should_subscribe=True):
		valid_sub_name = True
		if subscription == 'controller_buttons':
			await self.set_port_subscriptions([
				[self.BUTTONS_LEFT_PORT,1,0,should_subscribe],
				[self.BUTTONS_RIGHT_PORT,1,0,should_subscribe]
			])
			# 0: Only reports center buttons
			# 1, 2: Buggy "either press - or +" one time per side (can be opposites!)
			# 3: returns 0x0 and nothing else
			# 4: returns 0x0 0x0 0x0 and nothing else

		elif subscription == 'controller_rgb':
			await self.set_port_subscriptions([[self.RGB_LIGHT_PORT,0,5,should_subscribe]])
		elif subscription == 'controller_volts':
			await self.set_port_subscriptions([[self.CONTROLLER_VOLTS_PORT,0,5,should_subscribe]])
		elif subscription == 'controller_RSSI':
			await self.set_port_subscriptions([[self.CONTROLLER_RSSI_PORT,0,5,should_subscribe]])
		else:
			valid_sub_name = False

		if valid_sub_name:
			if should_subscribe:
				Controller.dp("Setting Controller subscription to "+subscription,2)
			else:
				Controller.dp("Removing Controller subscription to "+subscription,2)
		else:
			valid_sub_name = await super().set_subscription(subscription, should_subscribe)

		return valid_sub_name

	# ---- Make data useful ----

	# After getting the Value Format out of the controller, that allowed me to find this page
	# https://virantha.github.io/bricknil/lego_api/lego.html#remote-buttons
	def decode_button_data(self, port, data):
		if len(data) != 1:
			Controller.dp(self.system_type+" UNKNOWN BUTTON DATA, WEIRD LENGTH OF "+str(len(data))+":"+" ".join(hex(n) for n in data))
			# PORT 1: handset UNKNOWN BUTTON DATA, WEIRD LENGTH OF 3:0x0 0x0 0x0
			return

		side = 'left'		# A side
		if port == 1:
			side = 'right'	# B side

		button_id = data[0]
		if button_id == 0x0:
			self.message_queue.put(('controller_buttons',side,'zero'))
		elif button_id == 0x1:
			self.message_queue.put(('controller_buttons',side,'plus'))
		elif button_id == 0x7f:
			self.message_queue.put(('controller_buttons',side,'center'))
		elif button_id == 0xff:
			self.message_queue.put(('controller_buttons',side,'minus'))

		else:
			Controller.dp(self.system_type+" Unknown button "+hex(button_id))

	def decode_bt_rssi_data(self, data):
		# Lower numbers are larger distances from the computer
		rssi8 = int.from_bytes(data, byteorder="little", signed=True)
		Controller.dp("RSSI: "+str(rssi8))

	def decode_voltage_data(self,data):
		# FIXME: L or S and what do they mean?
		volts16 = int.from_bytes(data, byteorder="little", signed=False)
		Controller.dp("Voltage: "+str(volts16)+ " millivolts")

	# ---- Random stuff ----

	def dp(pstr, level=1):
		if Controller.DEBUG:
			if Controller.DEBUG >= level:
				print(pstr)

	# ---- Bluetooth port writes ----

	async def write_mode_data_RGB_color(self, port, color):
		if color not in Decoder.rgb_light_colors:
			return

		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x81,	# Command: port_output_command
			# end header
			port,
			0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
			0x51,	# Subcommand: WriteDirectModeData
			0x0,	# Mode (Could be 1 according to LEGO BTLE docs?)
			color
		])
		payload[0] = len(payload)
		# Controller.dp(self.system_type+" Debug RGB Write"+" ".join(hex(n) for n in payload))
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
		await asyncio.sleep(0.1)
