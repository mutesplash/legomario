import sys
import platform
import asyncio
import time
from bleak import BleakScanner, BleakClient
import io
import os
from pathlib import Path

from BTLegoMario import BTLegoMario

mario_devices = {}
json_code_file = "../mariocodes.json"

async def detect_device_callback(device, advertisement_data):
	global mario_devices
	global json_code_file

	if device:
		mario_device = BTLegoMario.which_device(advertisement_data)
		if mario_device:
			if not device.address in mario_devices:
				check_file = Path(os.path.expanduser(json_code_file))
				if check_file.is_file():
					with open(check_file, "rb") as f:
						mario_devices[device.address] = BTLegoMario(f.read())
				else:
					print("Known code database (mariocodes.json) NOT loaded!")
					mario_devices[device.address] = BTLegoMario()
				await mario_devices[device.address].connect(device, advertisement_data)
			else:
				if not mario_devices[device.address].connected:
					await mario_devices[device.address].connect(device, advertisement_data)
				else:
					print("Refusing to reconnect to "+mario_devices[device.address].which_brother)
		else:
			# "LEGO Mario_x_y"
			if device.name and device.name.startswith("LEGO Mario"):
				if advertisement_data and advertisement_data.manufacturer_data:
					print("UNKNOWN LEGO MARIO",mario_device, device.address, "RSSI:", device.rssi, advertisement_data)
				else:
					#print("Found some useless Mario broadcast without the manufacturer or service UUIDs")
					pass

async def callbackscan(duration=10):
	scanner = BleakScanner()
	print("Ready to find LEGO Mario!")
	scanner.register_detection_callback(detect_device_callback)
	print("Scanning...")
	await scanner.start()
	await asyncio.sleep(duration)
	await scanner.stop()

	#print("Scan results...")
	#for d in scanner.discovered_devices:
	#	print(d)

run_seconds = 60
asyncio.run(callbackscan(run_seconds))
if len(mario_devices):
	print("Done with LEGO Mario session after "+str(run_seconds)+" seconds...")
else:
	print("Didn't connect to a LEGO Mario.  Quitting.")
