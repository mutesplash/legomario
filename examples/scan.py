import asyncio
import time
from bleak import BleakScanner, BleakClient

import BTLego
from BTLego.MarioScanspace import MarioScanspace

mario_devices = {}
callbacks_to_device_addresses = {}
code_data = None

json_code_file = "../mariocodes.json"
run_seconds = 60

async def mariocallbacks(message):
	( cb_uuid, message_type, message_key, message_value ) = message

	print("CALLBACK:"+str(message))
	mario_device = mario_devices[callbacks_to_device_addresses[cb_uuid]]

	if message_type == 'scanner':
		if message_key == 'code':
			code_info = MarioScanspace.get_code_info(message_value[1])
			print("Scanned "+code_info['label'])

	if message_type == 'event' and message_key == 'coincount':
		coincount, coinsource = message_value
		print(f'Now have {coincount} coins total from {MarioScanspace.event_scanner_coinsource[coinsource]}')

async def detect_device_callback(device, advertisement_data):
	global mario_devices
	global callbacks_to_device_addresses

	if device:
		mario_device = BTLego.Decoder.determine_device_shortname(advertisement_data)
		if mario_device:
			if not device.address in mario_devices:
				mario_devices[device.address] = BTLego.Mario(advertisement_data)
				callback_uuid = await mario_devices[device.address].register_callback(mariocallbacks)
				callbacks_to_device_addresses[callback_uuid] = device.address
				await mario_devices[device.address].subscribe_to_messages_on_callback(callback_uuid, 'device_ready')
				await mario_devices[device.address].subscribe_to_messages_on_callback(callback_uuid, 'event')
#				await mario_devices[device.address].subscribe_to_messages_on_callback(callback_uuid, 'pants')
				await mario_devices[device.address].subscribe_to_messages_on_callback(callback_uuid, 'info')
				# You don't have to subscribe to "error" type messages...

				await mario_devices[device.address].connect(device, advertisement_data)

				await mario_devices[device.address].subscribe_to_messages_on_callback(callback_uuid, 'scanner', True)

			else:
				if not await mario_devices[device.address].is_connected():
					await mario_devices[device.address].connect(device, advertisement_data)
				else:
					print("Refusing to reconnect to "+mario_devices[device.address].system_type)
		else:
			# "LEGO Mario_x_y"
			# Spike prime hub starts with "LEGO Hub" but you have to pair with that, not BTLE
			if device.name and device.name.startswith("LEGO Mario"):
				if advertisement_data and advertisement_data.manufacturer_data:
					print("UNKNOWN LEGO MARIO",mario_device, device.address, "RSSI:", device.rssi, advertisement_data)
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

if not MarioScanspace.import_codefile(json_code_file):
	print(f'Known code database ({json_code_file}) NOT loaded!')

start_time = time.perf_counter()
try:
	asyncio.run(callbackscan(run_seconds))
except KeyboardInterrupt:
	print("Recieved keyboard interrupt, stopping.")
except asyncio.InvalidStateError:
	print("ERROR: Invalid state in Bluetooth stack, we're done here...")
stop_time = time.perf_counter()

if len(mario_devices):
	print(f'Done with LEGO Mario session after {int(stop_time - start_time)} seconds...')
else:
	print("Didn't connect to a LEGO Mario.  Quitting.")
