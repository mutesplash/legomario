# Setup
# -----
# * Connect any number of LEGO Mario devices to the computer running this app
#		(Try and not connect them at the same time or they'll connect to themselves)
# * Connect the LEGO 88010 controller to this app
#
# Use
# -----
# * Use the green controller button to switch which LEGO Mario device to control
#		(LED will change color to match)
# * Use the right +/- button to change the selected LEGO Mario device's volume by 10
# * Use the right center red button to power off the selected LEGO Mario device
# * Use the left center red button to power off the controller and end the program
#   after cycling through the LED colors

import asyncio
import time
from bleak import BleakScanner, BleakClient
from queue import SimpleQueue
import logging

import BTLego
from BTLego.MarioScanspace import MarioScanspace
from BTLego import Decoder
from BTLego.Decoder import LDev, HProp

MARIO_JSON_CODE_FILENAME = "../mariocodes.json"
run_seconds = 60

#BTLego.setLoggingLevel(logging.INFO)

temp_message_lastscan = None

sys_data = {
	'lego_devices': {},							# BLE_Subclasses
	'selected_device': None,
	'selected_device_index': -1
}

async def select_next_player(sys_data):
	is_a_handset = True
	counted_devices = 0
	while is_a_handset == True and counted_devices != len(sys_data['lego_devices']):
		sys_data['selected_device_index'] += 1
		counted_devices += 1
		if sys_data['selected_device_index']+1 > len(sys_data['lego_devices']):
			sys_data['selected_device_index'] = 0
		if sys_data['selected_device_index'] < len(list(sys_data['lego_devices'])):
			if not sys_data['lego_devices'][(list(sys_data['lego_devices'])[sys_data['selected_device_index']])].system_type == 'handset':
				is_a_handset = False
				break

	# Only handset
	if counted_devices == len(sys_data['lego_devices']) and is_a_handset:
		sys_data['selected_device_index'] = -1

	sys_data['selected_device'] = None
	rgb_color = None

	handset_device = find_first_device('handset')
	if handset_device:
		if not is_a_handset:
			sys_data['selected_device'] = sys_data['lego_devices'][list(sys_data['lego_devices'])[sys_data['selected_device_index']]]
			if sys_data['selected_device'].system_type == 'mario':
				rgb_color = 0x9
			elif sys_data['selected_device'].system_type == 'luigi':
				rgb_color = 0x6
			elif sys_data['selected_device'].system_type == 'peach':
				rgb_color = 0x1
		else:
			rgb_color = 0xa

	if rgb_color:
		async def set_rgb(this_device, rgb_color):
			await this_device.send_device_message(LDev.RGB, ('set_color',(rgb_color,)))
		BTLego.await_function_off_bleak_callback(set_rgb(handset_device, rgb_color))

async def mario_callback(message):
	# ( cb_uuid, type, key, value )
	global sys_data

	global temp_message_lastscan

	( cb_uuid, message_type, message_key, message_value ) = message

	print("M_CALLBACK:"+str(message))
	current_device = BTLego.device_for_callback_id(cb_uuid)

	# Find things that aren't in the table yet...
	if message_type == 'info' and message_key == 'connected':
		sys_data['lego_devices'][current_device.address] = current_device

	elif message_type == 'event':
		if message_key == 'scanner':
			scanner_code = MarioScanspace.get_code_info(message_value)
			temp_message_lastscan = scanner_code['label']
		elif message_key == 'coincount':
			if message_value[1] in MarioScanspace.event_scanner_coinsource:
				#print("This source is known as: "+BTLego.Mario.event_scanner_coinsource[message_value[1]])
				pass
			else:
				if temp_message_lastscan:
					print("Gained coins from last scan of "+temp_message_lastscan+" which is numbered "+str(message_value[1])+" and NOT KNOWN in the database!")
			temp_message_lastscan = None
	elif message_type == 'property':
		if message_key == HProp.MARIO_VOLUME:
#			print(f'MARIO VOLUME IS CURRENTLY {message_value}')
			setattr(current_device, 'volume', message_value)

async def controller_callback(message):
	global sys_data

	( cb_uuid, message_type, message_key, message_value ) = message

	print("C_CALLBACK:"+str(message))
	current_device = BTLego.device_for_callback_id(cb_uuid)

	if message_type == 'info' and message_key == 'connected':
		sys_data['lego_devices'][current_device.address] = current_device

	elif message_type == 'controller_buttons':
		if message_key == 'left' and message_value == 'center':
			async def turnoff_handset(current_device):
				if current_device:
					# Flip the light a bunch of colors and then turn off the controller
					for color in Decoder.rgb_light_colors:
						await current_device.send_device_message(LDev.RGB, ('set_color',(color,)))
					await current_device.turn_off()
					await asyncio.sleep(1)
				else:
					print('WHY IS THIS CALLBACK USING A DEAD OBJECT?')
			BTLego.await_function_off_bleak_callback(turnoff_handset(current_device))
			BTLego.await_function_off_bleak_callback(None)

		if message_key == 'right' and message_value == 'center':
			# Turn off the selected player
			if sys_data['selected_device_index'] != -1:
				sys_data['selected_device'] = sys_data['lego_devices'][list(sys_data['lego_devices'])[sys_data['selected_device_index']]]
				if sys_data['selected_device']:

					async def turnoff(sys_data, target_device):
						if target_device:
							await target_device.turn_off()
							sys_data['lego_devices'].pop(target_device.address, None)
							sys_data['selected_device'] = None
							sys_data['selected_device_index'] = -1

							await current_device.send_device_message(LDev.RGB, ('set_color',(0xa,)))
					BTLego.await_function_off_bleak_callback(turnoff(sys_data, sys_data['selected_device']))

		if message_key == 'right' and message_value == 'plus':
			if sys_data['selected_device']:
				set_volume = sys_data['selected_device'].volume + 10
				if set_volume > 100:
					set_volume = 10
				async def setvolume(sys_data):
					print("Cranking "+sys_data['selected_device'].system_type+" volume to "+str(set_volume))
					sys_data['selected_device'].volume = set_volume
					await sys_data['selected_device'].send_property_message( HProp.MARIO_VOLUME, ('set', set_volume) )
				BTLego.await_function_off_bleak_callback(setvolume(sys_data))

		if message_key == 'right' and message_value == 'minus':
			if sys_data['selected_device']:
				set_volume = sys_data['selected_device'].volume - 10
				if set_volume < 0:
					set_volume = 100
				async def setvolume(sys_data):
					print("Turning "+sys_data['selected_device'].system_type+" volume down to "+str(set_volume))
					sys_data['selected_device'].volume = set_volume
					await sys_data['selected_device'].send_property_message( HProp.MARIO_VOLUME, ('set', set_volume) )
				BTLego.await_function_off_bleak_callback(setvolume(sys_data))

	elif message_type == 'connection_request':
		if message_key == 'button' and message_value == 'down':
			# Change player the the right buttons control
			await select_next_player(sys_data)

def find_first_device(system_type):
	global sys_data
	for device_id in sys_data['lego_devices']:
		if sys_data['lego_devices'][device_id].system_type == system_type:
			return sys_data['lego_devices'][device_id]

callback_matcher = [
	{
		'device_match': [ 'handset' ],
		'event_callback': controller_callback,
		'requested_events': [ 'event', 'connection_request', 'controller_buttons', 'info' ]
	},
	{
		'device_match': [ 'anymario' ],
		'event_callback': mario_callback,
		'requested_events': [ 'event', 'property', 'info' ]
	}

]
BTLego.set_callbacks(callback_matcher)

if not MarioScanspace.import_codefile(MARIO_JSON_CODE_FILENAME):
	print(f'Known code database ({MARIO_JSON_CODE_FILENAME}) NOT loaded!')

BTLego.async_run(run_seconds)
