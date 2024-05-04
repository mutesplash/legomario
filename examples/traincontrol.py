# Setup
# -----
# * Connect the DUPLO Train Hub No. 5 to the computer running this app
# * Connect the LEGO 88010 controller to this app
#
# Use
# -----
# * Use the right +/- button to change the train's speed
# * Use the right center red button to immediately stop the train
# * Use the left +/- button to change the train's LED color
# * Use the left center red button to play a sound associated with the color

import logging
import asyncio
from bleak import BleakScanner, BleakClient

import BTLego
from BTLego import Decoder
from BTLego.Decoder import LDev

run_seconds = 240

train_device = None

color_to_sounds = {
	0x9: 0x3,	# red to brake
	0x2: 0x5,	# lilac to tune
	0x3: 0x7,	# blue to water
	0x7: 0x9,	# yellow to whistle
	0x6: 0xa	# green to horn
}

color_index = list(color_to_sounds.keys())

selected_color = -1

train_speed = 0

#BTLego.setLoggingLevel(logging.INFO)

async def train_callback(message):
	global train_device

	( cb_uuid, message_type, message_key, message_value ) = message

	print("TRAINBACK:"+str(message))
	current_device = BTLego.device_for_callback_id(cb_uuid)
	if not train_device:
		# Should get set by getting the info message from connect
		train_device = current_device

async def controller_callback(message):

	global color_to_sounds
	global selected_color
	global color_index

	global train_speed

	global train_device

	( cb_uuid, message_type, message_key, message_value ) = message

	print("CALLBACK:"+str(message))
	current_device = BTLego.device_for_callback_id(cb_uuid)

	if message_type == 'controller_buttons':
		# Beep
		if message_key == 'left' and message_value == 'center':
			if train_device:
				print(f'TRAIN BEEP')
				await train_device.send_device_message(LDev.DUPLO_BEEPER, ('play_sound',(color_to_sounds[color_index[selected_color]],)))

		# Stop
		if message_key == 'right' and message_value == 'center':
			train_speed = 0
			print(f'TRAIN SPEED {train_speed}')
			if train_device:
				await train_device.send_device_message(LDev.DUPLO_MOTOR, ('set_speed',(train_speed,)))

		# Accel
		if message_key == 'right' and message_value == 'plus':
			if train_speed < 100:
				train_speed += 10
			print(f'TRAIN SPEED {train_speed}')
			if train_device:
				await train_device.send_device_message(LDev.DUPLO_MOTOR, ('set_speed',(train_speed,)))

		# Decel
		if message_key == 'right' and message_value == 'minus':
			if train_speed > -100:
				train_speed -= 10
			print(f'TRAIN SPEED {train_speed}')
			if train_device:
				await train_device.send_device_message(LDev.DUPLO_MOTOR, ('set_speed',(train_speed,)))

		# Cycle LED up
		if message_key == 'left' and message_value == 'plus':
			selected_color += 1
			if selected_color >= len(color_index):
				selected_color = 0
			await current_device.send_device_message(LDev.RGB, ('set_color',(color_index[selected_color],)))
			if train_device:
				print(f'TRAIN COLOR')
				await train_device.send_device_message(LDev.RGB, ('set_color',(color_index[selected_color],)))

		# Cycle LED down
		if message_key == 'left' and message_value == 'minus':
			selected_color -= 1
			if selected_color < 0:
				selected_color = len(color_index)-1
			await current_device.send_device_message(LDev.RGB, ('set_color',(color_index[selected_color],)))
			if train_device:
				print(f'TRAIN COLOR')
				await train_device.send_device_message(LDev.RGB, ('set_color',(color_index[selected_color],)))


	elif message_type == 'connection_request':
		# Turn everything off if everything is connected
		if message_key == 'button' and message_value == 'down':
			if train_device:
				await train_device.turn_off()
				await current_device.turn_off()

callback_matcher = [
	{
		'device_match': [ 'handset' ],
		'event_callback': controller_callback,
		'requested_events': [ 'event', 'connection_request', 'controller_buttons', 'info' ]
	},
	{
		'device_match': [ 'duplotrain' ],
		'event_callback': train_callback,
		'requested_events': [ 'event', 'info']
	}

]

BTLego.set_callbacks(callback_matcher)

# If you want more control, just copy & modify the detection callback system out
# of BTLego/__init__.py that instantiates the BLE_Device, registers the callback,
# subscribes to messages, and connect()s it
run_seconds = 60
BTLego.async_run(run_seconds)

