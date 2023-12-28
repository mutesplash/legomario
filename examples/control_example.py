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

import asyncio
import time
from bleak import BleakScanner, BleakClient
from queue import SimpleQueue

import BTLego
from BTLego.MarioScanspace import MarioScanspace
from BTLego import Decoder

MARIO_JSON_CODE_FILENAME = "../mariocodes.json"
run_seconds = 60

temp_message_lastscan = None

sys_data = {
	'lego_devices': {},							# BLE_Subclasses
	'callbacks_to_device_addresses': {},	# mac addresses by BTLego callback UUID
	'session_over':False,
	'off_callback_functions': SimpleQueue(),	# Don't call back into a Bleak device on a Bleak callback, queue it

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
			await this_device.send_device_message(Decoder.io_type_id_ints['RGB Light'], ('set_color',(rgb_color,)))
		sys_data['off_callback_functions'].put(set_rgb(handset_device, rgb_color))

async def mario_callback(message):
	# ( cb_uuid, type, key, value )
	global sys_data

	global temp_message_lastscan

	( cb_uuid, message_type, message_key, message_value ) = message

	print("M_CALLBACK:"+str(message))
	current_device = sys_data['lego_devices'][sys_data['callbacks_to_device_addresses'][cb_uuid]]

	#mario_device = find_first_device('mario')
	#luigi_device = find_first_device('luigi')

	# Find things that aren't in the table yet...
	if message_type == 'event':
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
		if message_key == Decoder.hub_property_ints['Mario Volume']:
#			print(f'MARIO VOLUME IS CURRENTLY {message_value}')
			setattr(current_device, 'volume', message_value)

async def controller_callback(message):
	global sys_data

	( cb_uuid, message_type, message_key, message_value ) = message

	print("C_CALLBACK:"+str(message))
	current_device = sys_data['lego_devices'][sys_data['callbacks_to_device_addresses'][cb_uuid]]

	if message_type == 'controller_buttons':
		if message_key == 'left' and message_value == 'center':
			async def turnoff_handset(current_device):
				if current_device:
					# Flip the light a bunch of colors and then turn off the controller
					for color in Decoder.rgb_light_colors:
						await current_device.send_device_message(Decoder.io_type_id_ints['RGB Light'], ('set_color',(color,)))
					await current_device.turn_off()
					await asyncio.sleep(1)
				else:
					print('WHY IS THIS CALLBACK USING A DEAD OBJECT?')
			sys_data['off_callback_functions'].put(turnoff_handset(current_device))
			sys_data['off_callback_functions'].put(None)

		if message_key == 'right' and message_value == 'center':
			# Turn off the selected player
			if sys_data['selected_device_index'] != -1:
				sys_data['selected_device'] = sys_data['lego_devices'][list(sys_data['lego_devices'])[sys_data['selected_device_index']]]
				if sys_data['selected_device']:
					remove_these_callbacks = []
					for callback_id, devid in sys_data['callbacks_to_device_addresses'].items():
						if devid == sys_data['selected_device'].address:
							await sys_data['selected_device'].unregister_callback(callback_id)
							remove_these_callbacks.append(callback_id)
					for callback_id in remove_these_callbacks:
						sys_data['callbacks_to_device_addresses'].pop(callback_id, None)

					async def turnoff(sys_data, target_device):
						if target_device:
							await target_device.turn_off()
							sys_data['lego_devices'].pop(target_device.address, None)
							sys_data['selected_device'] = None
							sys_data['selected_device_index'] = -1

							handset_device = find_first_device('handset')
							if handset_device:
								await handset_device.send_device_message(Decoder.io_type_id_ints['RGB Light'], ('set_color',(0xa,)))
					sys_data['off_callback_functions'].put(turnoff(sys_data, sys_data['selected_device']))

		if message_key == 'right' and message_value == 'plus':
			if sys_data['selected_device']:
				set_volume = sys_data['selected_device'].volume + 10
				if set_volume > 100:
					set_volume = 10
				async def setvolume(sys_data):
					print("Cranking "+sys_data['selected_device'].system_type+" volume to "+str(set_volume))
					sys_data['selected_device'].volume = set_volume
					await sys_data['selected_device'].send_property_message( Decoder.hub_property_ints['Mario Volume'], ('set', set_volume) )
				sys_data['off_callback_functions'].put(setvolume(sys_data))

		if message_key == 'right' and message_value == 'minus':
			if sys_data['selected_device']:
				set_volume = sys_data['selected_device'].volume - 10
				if set_volume < 0:
					set_volume = 100
				async def setvolume(sys_data):
					print("Turning "+sys_data['selected_device'].system_type+" volume down to "+str(set_volume))
					sys_data['selected_device'].volume = set_volume
					await sys_data['selected_device'].send_property_message( Decoder.hub_property_ints['Mario Volume'], ('set', set_volume) )
				sys_data['off_callback_functions'].put(setvolume(sys_data))

	elif message_type == 'connection_request':
		if message_key == 'button' and message_value == 'down':
			# Change player the the right buttons control
			await select_next_player(sys_data)

def find_first_device(ad_name):
	global sys_data
	for device in sys_data['lego_devices']:
		if sys_data['lego_devices'][device].system_type == ad_name:
			return sys_data['lego_devices'][device]

async def detect_device_callback(bleak_device, advertisement_data):
	global sys_data

	if bleak_device:
		system_type = Decoder.determine_device_shortname(advertisement_data)
		if system_type:
			if not bleak_device.address in sys_data['lego_devices']:

				if system_type == 'handset':
					sys_data['lego_devices'][bleak_device.address] = BTLego.Controller(advertisement_data)
					callback_uuid = await sys_data['lego_devices'][bleak_device.address].register_callback(controller_callback)
					sys_data['callbacks_to_device_addresses'][callback_uuid] = bleak_device.address

					await sys_data['lego_devices'][bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'event')
					await sys_data['lego_devices'][bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'connection_request')
					await sys_data['lego_devices'][bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'controller_buttons')
					await sys_data['lego_devices'][bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'info')
				else:
					sys_data['lego_devices'][bleak_device.address] = BTLego.Mario(advertisement_data)
					callback_uuid = await sys_data['lego_devices'][bleak_device.address].register_callback(mario_callback)
					sys_data['callbacks_to_device_addresses'][callback_uuid] = bleak_device.address

					await sys_data['lego_devices'][bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'property')
					await sys_data['lego_devices'][bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'event')
					await sys_data['lego_devices'][bleak_device.address].subscribe_to_messages_on_callback(callback_uuid, 'info')

				await sys_data['lego_devices'][bleak_device.address].connect(bleak_device, advertisement_data)

				if system_type != 'handset':
					await sys_data['lego_devices'][bleak_device.address].send_property_message( Decoder.hub_property_ints['Mario Volume'], ('get', None) )
			else:
				if not await sys_data['lego_devices'][bleak_device.address].is_connected():
					await sys_data['lego_devices'][bleak_device.address].connect(bleak_device, advertisement_data)
				else:
					print("Refusing to reconnect to "+sys_data['lego_devices'][bleak_device.address].system_type)
		else:
			# "LEGO Mario_x_y"
			# Spike prime hub starts with "LEGO Hub" but you have to pair with that, not BTLE
			if bleak_device.name and bleak_device.name.startswith("LEGO Mario"):
				if advertisement_data and advertisement_data.manufacturer_data:
					print("UNKNOWN LEGO MARIO",system_type, bleak_device.address, "RSSI:", bleak_device.rssi, advertisement_data)
				else:
					#print("Found some useless Mario broadcast without the manufacturer or service UUIDs")
					pass

def lego_device_from_advertisement_data(advertisement_data):
	"""Generate a lego device from the given advertisement data"""
	global device_data

	devclass = Decoder.classname_from_ad_data(advertisement_data)
	if devclass:
		return devclass(advertisement_data)
	return None

async def drain_callback_calls(sys_data):
	try:
		while not sys_data['session_over']:
			while not sys_data['off_callback_functions'].empty():
				fpair = sys_data['off_callback_functions'].get()
				if not fpair:
					sys_data['session_over'] = True
				else:
					thisloop = asyncio.get_running_loop()
					if thisloop:
						if thisloop.is_running():
							print(f'DRAINING OFF-CALLBAKS {fpair}')
							await asyncio.create_task(fpair)
			await asyncio.sleep(0.1)
	except KeyboardInterrupt:
		print("Recieved keyboard interrupt, stopping callback function drain.")

async def callbackscan(sys_data, duration=10):
	try:
		scanner = BleakScanner(detect_device_callback)
		print("Ready to find LEGO Mario!")
		print("Scanning...")
		await scanner.start()
		start_time = time.perf_counter()

		while True:
			current_time = time.perf_counter()
			if current_time - start_time > duration:
				break
			if sys_data['session_over']:
				break
			await asyncio.sleep(1)

		await scanner.stop()
		sys_data['off_callback_functions'].put(None)
	except KeyboardInterrupt:
		print("Recieved keyboard interrupt, stopping scan.")


	#print("Scan results...")
	#for d in scanner.discovered_devices:
	#	print(d)

async def mainloop(run_seconds, sys_data):
	await asyncio.gather(
		callbackscan(sys_data, run_seconds),
		drain_callback_calls(sys_data)
	)

if not MarioScanspace.import_codefile(MARIO_JSON_CODE_FILENAME):
	print(f'Known code database ({MARIO_JSON_CODE_FILENAME}) NOT loaded!')

start_time = time.perf_counter()
try:
	asyncio.run(mainloop(run_seconds, sys_data))
except KeyboardInterrupt:
	print("Recieved keyboard interrupt, stopping.")
except asyncio.InvalidStateError:
	print("ERROR: Invalid state in Bluetooth stack, we're done here...")
stop_time = time.perf_counter()

if len(sys_data['lego_devices']):
	print(f'Done with LEGO Mario session after {int(stop_time - start_time)} seconds...')
	for address in sys_data['lego_devices']:
		asyncio.run(sys_data['lego_devices'][address].disconnect())
else:
	print("Didn't connect to a LEGO Mario.  Quitting.")
