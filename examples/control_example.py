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
# * Use the left center red button to power off the controller after cycling through the LED colors

import sys
import platform
import asyncio
import time
from bleak import BleakScanner, BleakClient
import io
import os
from pathlib import Path
import json

import BTLego

lego_devices = {}
callbacks_to_device_addresses = {}
code_data = None

json_code_file = "../mariocodes.json"
run_seconds = 60

volume = 0

temp_message_lastscan = None

selected_device = None
selected_device_index = -1

async def select_next_player():
	global lego_devices
	global selected_device
	global selected_device_index

	is_a_handset = True
	counted_devices = 0
	while is_a_handset == True and counted_devices != len(lego_devices):
		selected_device_index += 1
		counted_devices += 1
		if selected_device_index+1 > len(lego_devices):
			selected_device_index = 0
		if selected_device_index < len(list(lego_devices)):
			if not lego_devices[(list(lego_devices)[selected_device_index])].system_type == 'handset':
				is_a_handset = False
				break

	# Only handset
	if counted_devices == len(lego_devices) and is_a_handset:
		selected_device_index = -1

	selected_device = None

	handset_device = find_first_device('handset')
	if handset_device:
		if not is_a_handset:
			selected_device = lego_devices[list(lego_devices)[selected_device_index]]
			if selected_device.system_type == 'mario':
				await handset_device.write_mode_data_RGB_color(0x9)
				await asyncio.sleep(0.2)
			elif selected_device.system_type == 'luigi':
				await handset_device.write_mode_data_RGB_color(0x6)
				await asyncio.sleep(0.2)
			elif selected_device.system_type == 'peach':
				await handset_device.write_mode_data_RGB_color(0x1)
				await asyncio.sleep(0.2)
		else:
			await handset_device.write_mode_data_RGB_color(0xa)
			await asyncio.sleep(0.2)

async def mario_callback(message):
	# ( dev_addr, type, key, value )
	global lego_devices
	global callbacks_to_device_addresses

	global temp_message_lastscan

	print("CALLBACK:"+str(message))
	current_device = lego_devices[callbacks_to_device_addresses[message[0]]]

	#mario_device = find_first_device('mario')
	#luigi_device = find_first_device('luigi')

	# Find things that aren't in the table yet...
	if message[1] == 'event':
		if message[2] == 'scanner':
			scanner_code = BTLego.Mario.get_code_info(message[3])
			temp_message_lastscan = scanner_code['label']
		elif message[2] == 'coincount':
			if message[3][1] in BTLego.Mario.event_scanner_coinsource:
				#print("This source is known as: "+BTLego.Mario.event_scanner_coinsource[message[3][1]])
				pass
			else:
				if temp_message_lastscan:
					print("Gained coins from last scan of "+temp_message_lastscan+" which is numbered "+str(message[3][1])+" and NOT KNOWN in the database!")
			temp_message_lastscan = None


async def controller_callback(message):
	global volume
	global selected_device
	global selected_device_index

	global lego_devices
	global callbacks_to_device_addresses

	print("CALLBACK:"+str(message))
	current_device = lego_devices[callbacks_to_device_addresses[message[0]]]

	if message[1] == 'controller_buttons':
		if message[2] == 'left' and message[3] == 'center':
			# Flip the light a bunch of colors and then turn off the controller
			for color in BTLego.Decoder.rgb_light_colors:
				await current_device.write_mode_data_RGB_color(color)
				await asyncio.sleep(0.2)
			await current_device.turn_off()

			await asyncio.sleep(0.2)

		if message[2] == 'right' and message[3] == 'center':
			# Turn off the selected player
			if selected_device_index != -1:
				selected_device = lego_devices[list(lego_devices)[selected_device_index]]
				if selected_device:
					remove_these_callbacks = []
					for callback_id, devid in callbacks_to_device_addresses.items():
						if devid == selected_device.address:
							await selected_device.unregister_callback(callback_id)
							remove_these_callbacks.append(callback_id)
					for callback_id in remove_these_callbacks:
						callbacks_to_device_addresses.pop(callback_id, None)

					await selected_device.turn_off()
					lego_devices.pop(selected_device.address, None)
					selected_device = None
					selected_device_index = -1

					handset_device = find_first_device('handset')
					if handset_device:
						await handset_device.write_mode_data_RGB_color(0xa)
						await asyncio.sleep(0.2)

		if message[2] == 'right' and message[3] == 'plus':
			if selected_device:
				set_volume = selected_device.volume + 10
				if set_volume > 100:
					set_volume = 10
				print("Cranking "+selected_device.system_type+" volume to "+str(set_volume))
				await selected_device.set_volume(set_volume)

		if message[2] == 'right' and message[3] == 'minus':
			if selected_device:
				set_volume = selected_device.volume - 10
				if set_volume < 0:
					set_volume = 100
				print("Turning "+selected_device.system_type+" volume down to "+str(set_volume))
				await selected_device.set_volume(set_volume)

	elif message[1] == 'event':
		if message[2] == 'button' and message[3] == 'pressed':
			# Change player the the right buttons control
			await select_next_player()

def find_first_device(ad_name):
	global lego_devices
	for device in lego_devices:
		if lego_devices[device].system_type == ad_name:
			return lego_devices[device]

async def detect_device_callback(bleak_device, advertisement_data):
	global lego_devices
	global callbacks_to_device_addresses
	global code_data

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
#					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'controller_volts')
#					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'controller_RSSI')
					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'info')
				else:
					lego_devices[bleak_device.address] = BTLego.Mario(advertisement_data,code_data)
					callback_uuid = await lego_devices[bleak_device.address].register_callback(mario_callback)
					callbacks_to_device_addresses[callback_uuid] = bleak_device.address

					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'event')
	#				await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'pants')
					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'info')
#					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'gesture')
#					await lego_devices[bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'scanner', True)



				await lego_devices[bleak_device.address].connect(bleak_device, advertisement_data)
			else:
				if not await lego_devices[bleak_device.address].is_connected():
					await lego_devices[bleak_device.address].connect(bleak_device, advertisement_data)
				else:
					print("Refusing to reconnect to "+lego_devices[bleak_device.address].system_type)
		else:
			# "LEGO Mario_x_y"
			# Spike prime hub starts with "LEGO Hub" but you have to pair with that, not BTLE
			if bleak_device.name and bleak_device.name.startswith("LEGO Mario"):
				if advertisement_data and advertisement_data.manufacturer_data:
					print("UNKNOWN LEGO MARIO",system_type, bleak_device.address, "RSSI:", bleak_device.rssi, advertisement_data)
				else:
					#print("Found some useless Mario broadcast without the manufacturer or service UUIDs")
					pass

async def callbackscan(duration=10):
	scanner = BleakScanner(detect_device_callback)
	print("Ready to find LEGO Mario!")
	print("Scanning...")
	await scanner.start()
	await asyncio.sleep(duration)
	await scanner.stop()

	#print("Scan results...")
	#for d in scanner.discovered_devices:
	#	print(d)

check_file = Path(os.path.expanduser(json_code_file))
if check_file.is_file():
	with open(check_file, "rb") as f:
		try:
			code_data = json.loads(f.read())
		except ValueError as e:  # also JSONDecodeError
			print("Unable to load code translation JSON:"+str(e))

if not code_data:
	print("Known code database (mariocodes.json) NOT loaded!")

start_time = time.perf_counter()
try:
	asyncio.run(callbackscan(run_seconds))
except KeyboardInterrupt:
	print("Recieved keyboard interrupt, stopping.")
except asyncio.exceptions.InvalidStateError:
	print("ERROR: Invalid state in Bluetooth stack, we're done here...")
stop_time = time.perf_counter()

if len(lego_devices):
	print(f'Done with LEGO Mario session after {int(stop_time - start_time)} seconds...')
else:
	print("Didn't connect to a LEGO Mario.  Quitting.")
