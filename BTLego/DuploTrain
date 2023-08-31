import asyncio

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder

class DuploTrain(BLE_Device):
	# 0:	Don't debug
	# 1:	Print weird stuff
	# 2:	Print most of the information flow
	# 3:	Print stuff even you the debugger probably don't need
	DEBUG = 0

	message_types = (
		'duplotrain_rgb',
		'duplotrain_color',
		'duplotrain_motor',
		'duplotrain_speed'
	)

	tone_numbers = {
		0x0:'none',
		0x3:'low',		# White tile, light off
		0x9:'medium',
		0xa:'high'		# White tile, light on
	}

	sound_numbers = {
		0x0:'none',
		0x3:'brake',	# Red tile
		0x5:'tune',		# ? what makes THIS ?
		0x7:'water',	# pretend_default_blue_tile
		0x9:'whistle',	# Yellow tile
		0xa:'horn',		# pretend_default_green_tile
	}

	ui_beep_numbers = {
		0x0:'none',
		0x1:'beep beep (low)',
		0x2:'beep',
		0x3:'turn off',
		#0x4 invalid
		0x5:'bluetooth disconnect',
		#0x6 invalid
		0x7:'bluetooth connect',
		#0x8 invalid
		0x9:'turn on',
		0xa:'beep beep beep',
	}

	MOTOR_PORT = 0x0
	BEEPER_PORT = 0x1
	RGB_LIGHT_PORT = 0x11		# 17
	COLOR_SENSOR_PORT = 0x12	# 18
	VOLTAGE_PORT = 0x14			# 20
	SPEED_PORT = 0x3c			# 60

	BEEP_MODE_TONE = 0
	BEEP_MODE_SOUND = 1
	BEEP_MODE_UI_BEEPS = 2

	LED_RGB_MODE = 1
	LED_COLOR_MODE = 0

	# Overrideable
	async def _inital_connect_updates(self):
		await self.request_name_update()
		await self.request_version_update()

		# Use as a guaranteed init event
		await self.request_battery_update()

		#await self._demo_range_test()

	async def _demo_range_test(self):

		print("Testing...")

		# "ONSEC"
		# stalls it out
		#await self._set_port_subscriptions([[self.MOTOR_PORT, 1,1,0 ]])
		# Lets it go (but not to the "current" speed)
		#await self._set_port_subscriptions([[self.MOTOR_PORT, 0,1,0 ]])

#		await self.write_mode_motor_speed(-50)
#		await asyncio.sleep(2)

#		await asyncio.sleep(0.42)	# Maximum wait if the thing only accepts motor speeds in pulses or whatever is happening there
#		await self.write_mode_motor_speed(50)

#		await asyncio.sleep(2)
#		await self.write_mode_motor_speed(0)


# Yep
#		await self.pretend_default_blue_tile()
#		await asyncio.sleep(2)
#		await self.pretend_default_green_tile()
#		await asyncio.sleep(2)

# Yep
#		await self._set_port_subscriptions([[self.BEEPER_PORT, self.BEEP_MODE_TONE,1,0 ]])
#		for tone in self.tone_numbers:
#			await self.write_mode_data_play_noise(tone, self.BEEP_MODE_TONE)
#			await asyncio.sleep(1)

# Yep
#		await self._set_port_subscriptions([[self.BEEPER_PORT, self.BEEP_MODE_SOUND,1,0 ]])
#		for sound in self.sound_numbers:
#			await self.write_mode_data_play_noise(sound, self.BEEP_MODE_SOUND)
#			await asyncio.sleep(2)

# Yep
#		await self._set_port_subscriptions([[self.BEEPER_PORT,self.BEEP_MODE_UI_BEEPS,1,0 ]])
#		for ui_sound in self.ui_beep_numbers:
#			await self.write_mode_data_play_noise(ui_sound, self.BEEP_MODE_UI_BEEPS)
#			await asyncio.sleep(2)

# Yep
#		await self._set_port_subscriptions([[self.RGB_LIGHT_PORT,self.LED_COLOR_MODE,1,0 ]])
#		for color in Decoder.rgb_light_colors:
#			await self.write_mode_data_light_color(color)
#			await asyncio.sleep(0.2)

# Yep
#		await self._set_port_subscriptions([[self.RGB_LIGHT_PORT,self.LED_RGB_MODE,1,0 ]])
#		for red in range(0,256,64):
#			for green in range(0,256,64):
#				for blue in range(0,256,64):
#					await self.write_mode_data_RGB_bytes(red, green, blue)
#					await asyncio.sleep(0.1)

#		await self.turn_off()
		pass

	# Override
	# add message_types, got to do this...
	def _reset_event_subscription_counters(self):
		for message_type in self.message_types:
			self.BLE_event_subscriptions[message_type] = 0;
		super()._reset_event_subscription_counters()

	# Override
	# True if message_type is valid, false otherwise
	async def _set_BLE_subscription(self, message_type, should_subscribe=True):

		valid_sub_name = True

		if message_type == 'duplotrain_rgb':
			await self._set_port_subscriptions([[self.RGB_LIGHT_PORT,0,5,should_subscribe]])
			await self._set_port_subscriptions([[self.RGB_LIGHT_PORT,1,5,should_subscribe]])
		elif message_type == 'duplotrain_color':
			await self._set_port_subscriptions([[self.COLOR_SENSOR_PORT,0,5,should_subscribe]])
			await self._set_port_subscriptions([[self.COLOR_SENSOR_PORT,1,5,should_subscribe]])
			await self._set_port_subscriptions([[self.COLOR_SENSOR_PORT,2,5,should_subscribe]])
			await self._set_port_subscriptions([[self.COLOR_SENSOR_PORT,3,5,should_subscribe]])
			await self._set_port_subscriptions([[self.COLOR_SENSOR_PORT,4,5,should_subscribe]])
		elif message_type == 'duplotrain_motor':
			await self._set_port_subscriptions([[self.MOTOR_PORT,0,5,should_subscribe]])
			await self._set_port_subscriptions([[self.MOTOR_PORT,1,5,should_subscribe]])
		elif message_type == 'duplotrain_speed':
			# Same as mario gesture int size
			await self._set_port_subscriptions([[self.SPEED_PORT,0,5,should_subscribe]])
			await self._set_port_subscriptions([[self.SPEED_PORT,1,5,should_subscribe]])
			await self._set_port_subscriptions([[self.SPEED_PORT,2,5,should_subscribe]])
		else:
			valid_sub_name = False

		if valid_sub_name:
			BLE_Device.dp(f'{self.system_type} set DuploTrain hardware messages for {message_type} to {should_subscribe}',2)
		else:
			# No passthrough
			valid_sub_name = await super()._set_BLE_subscription(message_type, should_subscribe)

		return valid_sub_name

	# ---- Make data useful ----

	# ---- Random stuff ----

	def dp(pstr, level=1):
		if DuploTrain.DEBUG:
			if DuploTrain.DEBUG >= level:
				print(pstr)

	# ---- Bluetooth port writes ----

	async def pretend_default_blue_tile(self):
		await self._set_port_subscriptions([[self.BEEPER_PORT, self.BEEP_MODE_SOUND,1,0 ]])
		await self.write_mode_data_play_noise(0x3, self.BEEP_MODE_SOUND)
		await asyncio.sleep(1.1)
		await self.write_mode_data_play_noise(0x7, self.BEEP_MODE_SOUND)
		await asyncio.sleep(1.2)
		await self.write_mode_data_play_noise(0x7, self.BEEP_MODE_SOUND)
		await asyncio.sleep(1.2)
		await self.write_mode_data_play_noise(0x7, self.BEEP_MODE_SOUND)
		await asyncio.sleep(1.2)
		await self.write_mode_data_play_noise(0x7, self.BEEP_MODE_SOUND)

	async def pretend_default_green_tile(self):
		await self._set_port_subscriptions([[self.BEEPER_PORT, self.BEEP_MODE_SOUND,1,0 ]])
		await self.write_mode_data_play_noise(0x3, self.BEEP_MODE_SOUND)
		await asyncio.sleep(1)
		await self.write_mode_data_play_noise(0xa, self.BEEP_MODE_SOUND)

	# FIXME: If you let mere mortals write this, you gotta verify the port and color vars

	async def write_mode_data_light_color(self, color):
		if color not in Decoder.rgb_light_colors:
			return

		payload = bytearray([
			0x7,	# len
			0x0,	# padding/unused hub id
			0x81,	# Command: port_output_command
			# end header
			self.RGB_LIGHT_PORT,
			0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
					# Node poweredup uses 0x11 here always
			0x51,	# Subcommand: WriteDirectModeData
			0x0,	# Mode "COL O", or just because the docs say put 0x0 here
			color
		])
		payload[0] = len(payload)
#		DuploTrain.dp(self.system_type+" Debug color Write: "+" ".join(hex(n) for n in payload))
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
		await asyncio.sleep(0.1)

	# Hat tip to legoino (Lpf2Hub.cpp) for noting that you have to do the port input format setup
	# to change the input mode instead of just yolo sending it (because that doesn't work)
	# I guess the docs _kind of_ say that but they'e not really easy to interpret
	async def write_mode_data_RGB_bytes(self, red, green, blue):

		def nomalize_color(c):
			if c > 255:
				c = 255
			if c < 0:
				c = 0
			return c
		red = nomalize_color(red)
		green = nomalize_color(green)
		blue = nomalize_color(blue)

		payload = bytearray([
			0x10,	# len
			0x0,	# padding
			0x81,	# Command: port_output_command
			# end header
			self.RGB_LIGHT_PORT,
			0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
					# Node poweredup uses 0x11 here always
			0x51,	# Subcommand: WriteDirectModeData
			0x1,	# Mode 1 "RGB O", or just because the docs say put 0x1 here
			red,
			green,
			blue
		])
		payload[0] = len(payload)
		# DuploTrain.dp(self.system_type+" Debug RGB Write"+" ".join(hex(n) for n in payload))
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
		await asyncio.sleep(0.1)

	async def write_mode_data_play_noise(self, noise_id, noise_mode):
		# FIXME: Doesn't verify squat
		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x81,	# Command: port_output_command
			# end header
			self.BEEPER_PORT,
			0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
					# Node poweredup and legoino use 0x11 here always
			0x51,	# Subcommand: WriteDirectModeData
			noise_mode,	# Mode 0 is just high/med/low tones, Mode 1 is interactive sounds, Mode 2 is beeps the UI typically makes
			noise_id
		])
		payload[0] = len(payload)

		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
		await asyncio.sleep(0.1)

	async def write_mode_motor_speed(self, speed):
		# -100 to 100
		# Somehow got it in a weird mode where the movement would need a 0.42 sec gap between speed commands to go smoothly

		converted_speed = DuploTrain.set_percent_speed_range_to_port_int(speed)
		print(f'Converted {speed} to {converted_speed}')

		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x81,	# Command: port_output_command
			# end header
			self.MOTOR_PORT,
			0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
					# Node poweredup and legoino use 0x11 here always
			0x51,	# Subcommand: WriteDirectModeData
			0x0,	# FIXME: WHAT is this?
			converted_speed
		])
		payload[0] = len(payload)

		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
		await asyncio.sleep(0.1)

	def set_percent_speed_range_to_port_int(speed):

		# This doesn't make a lot of sense to me, but the speed is
		# 0-100 forwards (lead with light) and 156-255 backwards

		if speed > 100:
			return 100

		if speed >= 0:
			return speed

		if speed < -100:
			return 156

		return 256 + speed
