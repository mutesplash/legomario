# Setup
# -----
# * Connect any hub with the RGB device to the computer running this app
# * Connect the LEGO 88010 controller to this app
#
# Note: The controller will connect directly to boostmove if you pair them
# at the same time.  Boostmove will also get bored and disconnect if you
# don't talk to it (change the color) soon enough.
#
# Use
# -----
# * Use the left +/- button to change the hub's LED color

import logging
import asyncio
from bleak import BleakScanner, BleakClient

import BTLego
from BTLego import Decoder
from BTLego.Decoder import LDev

hub_devices = []

color_index = list(Decoder.rgb_light_colors.keys())

selected_color = -1
rgb = {
	'red':0,
	'green':0,
	'blue':0,
	'selected':"red"
}

#BTLego.setLoggingLevel(logging.INFO)

async def hub_callback(message):
	global hub_devices

	( cb_uuid, message_type, message_key, message_value ) = message

	print("HUBBACK:"+str(message))
	current_device = BTLego.device_for_callback_id(cb_uuid)
	if current_device not in hub_devices:
		hub_devices.append(current_device)
		# Should get set by getting the info message from connect

async def controller_callback(message):

	global color_to_sounds
	global selected_color
	global color_index

	global hub_devices
	global rgb

	( cb_uuid, message_type, message_key, message_value ) = message

	print("CALLBACK:"+str(message))
	current_device = BTLego.device_for_callback_id(cb_uuid)

	if message_type == 'controller_buttons':
		# Cycle LED up
		if message_key == 'left':
			if message_value == 'plus':
				def flip_rgb_up(rgb):
					if rgb['selected'] == "green":
						rgb['green'] = rgb['green'] + 16
						if rgb['green'] > 255:
							rgb['green'] = 255
					if rgb['selected'] == "red":
						rgb['red'] = rgb['red'] + 16
						if rgb['red'] > 255:
							rgb['red'] = 255
					if rgb['selected'] == "blue":
						rgb['blue'] = rgb['blue'] + 16
						if rgb['blue'] > 255:
							rgb['blue'] = 255
					return (rgb['red'], rgb['green'], rgb['blue'])

				command = ('set_rgb', flip_rgb_up(rgb))
				current_device.send_device_message(LDev.RGB, command)
				if hub_devices:
					for hub_device in hub_devices:
						print(f'HUB RGB COLOR')
						hub_device.send_device_message(LDev.RGB, command)

			# Cycle LED down
			elif message_value == 'minus':
				def flip_rgb_down(rgb):
					if rgb['selected'] == "green":
						rgb['green'] = rgb['green'] - 16
						if rgb['green'] < 0:
							rgb['green'] = 0
					if rgb['selected'] == "red":
						rgb['red'] = rgb['red'] - 16
						if rgb['red'] < 0:
							rgb['red'] = 0
					if rgb['selected'] == "blue":
						rgb['blue'] = rgb['blue'] - 16
						if rgb['blue'] < 0:
							rgb['blue'] = 0
					return (rgb['red'], rgb['green'], rgb['blue'])
				command = ('set_rgb',flip_rgb_down(rgb))
				current_device.send_device_message(LDev.RGB, command)
				if hub_devices:
					for hub_device in hub_devices:
						print(f'HUB RGB COLOR')
						hub_device.send_device_message(LDev.RGB, command)

			elif message_value == 'center':
				if rgb['selected'] == "green":
					rgb['selected'] = "blue"
				elif rgb['selected'] == "red":
					rgb['selected'] = "green"
				elif rgb['selected'] == "blue":
					rgb['selected'] = "red"

		elif message_key == 'right':
			if message_value == 'plus':
				selected_color += 1
				if selected_color >= len(color_index):
					selected_color = 0
				command = ('set_color', (color_index[selected_color],))
				current_device.send_device_message(LDev.RGB, command)
				if hub_devices:
					for hub_device in hub_devices:
						print(f'HUB RGB COLOR')
						hub_device.send_device_message(LDev.RGB, command)

			elif message_value == 'minus':
				selected_color -= 1
				if selected_color < 0:
					selected_color = len(color_index)-1
				command = ('set_color',(color_index[selected_color],))
				current_device.send_device_message(LDev.RGB, command)
				if hub_devices:
					for hub_device in hub_devices:
						print(f'HUB RGB COLOR')
						hub_device.send_device_message(LDev.RGB, command)

	elif message_type == 'connection_request':
		# Turn everything off if everything is connected
		if message_key == 'button' and message_value == 'down':
			if hub_devices:
				for hub_device in hub_devices:
					hub_device.turn_off()
			if current_device:
				current_device.turn_off()

callback_matcher = [
	{
		'device_match': [ 'handset' ],
		'event_callback': controller_callback,
		'requested_events': [ 'event', 'connection_request', 'controller_buttons', 'info' ]
	},
	{
		'device_match': [ 'wedo2', 'spikesmall', 'boostmove', 'technicmove', 'hub_2', 'hub_4', 'duplotrain' ],
		'event_callback': hub_callback,
		'requested_events': [ 'event', 'info']
	}

]

BTLego.set_callbacks(callback_matcher)

# If you want more control, just copy & modify the detection callback system out
# of BTLego/__init__.py that instantiates the BLE_Device, registers the callback,
# subscribes to messages, and connect()s it
run_seconds = 6000
BTLego.async_run(run_seconds)

