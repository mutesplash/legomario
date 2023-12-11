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

import sys
import platform
import asyncio
import time
from bleak import BleakScanner, BleakClient
import io
import os
from pathlib import Path

import BTLego

lego_devices = {}
callbacks_to_device_addresses = {}
code_data = None

run_seconds = 240

temp_message_lastscan = None

train_device = None
train_device_index = -1

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

async def train_callback(message):
	# ( dev_addr, type, key, value )
	global lego_devices
	global callbacks_to_device_addresses

	global color_to_sounds
	global selected_color
	global color_index

	global train_speed

	global train_device
	global train_device_index

	print("TRAINBACK:"+str(message))
	current_device = lego_devices[callbacks_to_device_addresses[message[0]]]



async def controller_callback(message):

	global color_to_sounds
	global selected_color
	global color_index

	global train_speed

	global train_device
	global train_device_index

	global lego_devices
	global callbacks_to_device_addresses

	print("CALLBACK:"+str(message))
	current_device = lego_devices[callbacks_to_device_addresses[message[0]]]

	if message[1] == 'controller_buttons':
		# Beep
		if message[2] == 'left' and message[3] == 'center':
			if train_device:
				# FIXME: Internal call
				print(f'TRAIN BEEP')
				await train_device._set_port_subscriptions([[train_device.BEEPER_PORT, train_device.BEEP_MODE_SOUND,1,0 ]])
				await train_device.write_mode_data_play_noise(color_to_sounds[color_index[selected_color]], train_device.BEEP_MODE_SOUND)

		# Stop
		if message[2] == 'right' and message[3] == 'center':
			train_speed = 0
			print(f'TRAIN SPEED {train_speed}')
			if train_device:
				await train_device.write_mode_motor_speed(train_speed)

		# Accel
		if message[2] == 'right' and message[3] == 'plus':
			if train_speed < 100:
				train_speed += 10
			print(f'TRAIN SPEED {train_speed}')
			if train_device:
				await train_device.write_mode_motor_speed(train_speed)

		# Decel
		if message[2] == 'right' and message[3] == 'minus':
			if train_speed > -100:
				train_speed -= 10
			print(f'TRAIN SPEED {train_speed}')
			if train_device:
				await train_device.write_mode_motor_speed(train_speed)

		# Cycle LED
		if message[2] == 'left' and message[3] == 'plus':
			selected_color += 1
			if selected_color >= len(color_index):
				selected_color = 0
			await current_device.write_mode_data_RGB_color(color_index[selected_color])
			if train_device:
				print(f'TRAIN COLOR')
				await train_device._set_port_subscriptions([[train_device.RGB_LIGHT_PORT,train_device.LED_COLOR_MODE,1,0 ]])
				await train_device.write_mode_data_light_color(color_index[selected_color])

		# Cycle LED
		if message[2] == 'left' and message[3] == 'minus':
			selected_color -= 1
			if selected_color < 0:
				selected_color = len(color_index)-1
			await current_device.write_mode_data_RGB_color(color_index[selected_color])
			if train_device:
				print(f'TRAIN COLOR')
				await train_device._set_port_subscriptions([[train_device.RGB_LIGHT_PORT,train_device.LED_COLOR_MODE,1,0 ]])
				await train_device.write_mode_data_light_color(color_index[selected_color])


	elif message[1] == 'event':
		if message[2] == 'button' and message[3] == 'pressed':
			# Change player the the right buttons control
			if train_device:
				await train_device.turn_off()
				await current_device.turn_off()

async def detect_device_callback(bleak_device, advertisement_data):
	global lego_devices
	global callbacks_to_device_addresses
	global code_data
	global train_device

	if bleak_device:
		system_type = BTLego.Decoder.determine_device_shortname(advertisement_data)
		if system_type:
			if not bleak_device.address in lego_devices:

				if system_type == 'handset':
					lego_devices[bleak_device.address] = BTLego.Controller(advertisement_data)
					callback_uuid = await lego_devices[bleak_device.address].register_callback(controller_callback)
					callbacks_to_device_addresses[callback_uuid] = bleak_device.address

					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'event')
					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'controller_buttons')
#					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'connection_request')
#					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'controller_rgb')
					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'info')
				elif system_type == 'duplotrain':
					lego_devices[bleak_device.address] = BTLego.DuploTrain(advertisement_data)
					train_device = lego_devices[bleak_device.address]
					callback_uuid = await lego_devices[bleak_device.address].register_callback(train_callback)
					callbacks_to_device_addresses[callback_uuid] = bleak_device.address

					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'event')
					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'info')
				else:
					print("UNHANDLED LEGO DEVICE",system_type, bleak_device.address, advertisement_data)

				if bleak_device.address in lego_devices:
					await lego_devices[bleak_device.address].connect(bleak_device, advertisement_data)
			else:
				if not await lego_devices[bleak_device.address].is_connected():
					await lego_devices[bleak_device.address].connect(bleak_device, advertisement_data)
				else:
					print("Refusing to reconnect to "+lego_devices[bleak_device.address].system_type)

async def callbackscan(duration=10):
	scanner = BleakScanner(detect_device_callback)
	print("Ready to find LEGO BTLE devices!")
	print("Scanning...")
	await scanner.start()
	await asyncio.sleep(duration)
	await scanner.stop()

start_time = time.perf_counter()
try:
	asyncio.run(callbackscan(run_seconds))
except KeyboardInterrupt:
	print("Recieved keyboard interrupt, stopping.")
except asyncio.exceptions.InvalidStateError:
	print("ERROR: Invalid state in Bluetooth stack, we're done here...")
stop_time = time.perf_counter()

if len(lego_devices):
	print(f'Done with LEGO bluetooth session after {int(stop_time - start_time)} seconds...')
else:
	print("Didn't connect to a LEGO device.  Quitting.")
