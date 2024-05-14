import logging
import sys
import time
import asyncio
from bleak import BleakScanner, BleakClient

from .Controller import Controller
from .Mario import Mario
from .Decoder import Decoder
from .DuploTrain import DuploTrain
from .Hub2 import Hub2
from .Jajur1 import Jajur1

from queue import SimpleQueue

__lego_devices__ = {}
__callbacks_to_device_addresses__ = {}
__callback_matcher__ = []
__off_bleak_callback_queue__ = SimpleQueue()
__running__ = False

def setLoggingLevel(level):
	logger = logging.getLogger(__name__)
	logger.setLevel(level)

	if not logger.hasHandlers():
		logger.addHandler(logging.StreamHandler(sys.stdout))

def set_callbacks(callback_matcher):
	global __callback_matcher__

	#FIXME: You should probably verify this structure
	__callback_matcher__ = callback_matcher

	for callback in callback_matcher:
		if 'device_match' in callback:
			# BTLego.Decoder.advertised_system_type
			# [ 'Peach', 'LEGO Mario_f_r', 'AnyMario', 'hub_2' ],
			pass
		if 'event_callback' in callback:
			# mariocallbacks
			pass
		if 'requested_events' in callback:
			for requested_event in callback['requested_events']:
				# [ 'event', 'device_ready', 'scanner' ]
				pass

def device_for_callback_id(cb_id):
	return __lego_devices__[__callbacks_to_device_addresses__[cb_id]]

def await_function_off_bleak_callback(async_function):
	"""
	If you try and await functions in the callback provided to set_callbacks(),
	you'll end up blocking Bleak's messaging.  Instead, stuff them on this queue
	to be processed concurrently with Bleak using asyncio.gather()

	Now, you still can block YOURSELF during the processing of this queue...

	To collapse both loops and quit async_run(), call this function with None
	"""
	__off_bleak_callback_queue__.put(async_function)

def __match_up_device(bluetooth_name, dev_systype, dev_shortname):
	logger = logging.getLogger(__name__)

	retval = []
	for callback in __callback_matcher__:
		if 'device_match' in callback:
			for supplied_devmatch in callback['device_match']:

				normalized_supplied_devmatch = supplied_devmatch.lower()

				if normalized_supplied_devmatch == dev_shortname.lower():
					logger.debug(f'Will connect to device matched by device type {dev_shortname}')
					retval.append(callback)
					# Hey, so if you leave the handset default name, guess what happens if you didn't
					# continue and fall through instead? Duplicate messages!  FIXME: may need to rethink this
					continue
				if normalized_supplied_devmatch == 'anymario' and Decoder.ble_dev_classes[dev_systype] == 'Mario':
					logger.debug(f'Will connect to {dev_shortname} as it is AnyMario')
					retval.append(callback)
					# I guess you could also name your thing anymario too... FIXME
					continue
				if bluetooth_name is not None and normalized_supplied_devmatch == bluetooth_name.lower():
					logger.debug(f'Will connect to exact name {bluetooth_name}')
					retval.append(callback)
				# I didn't put MAC address matching in here because MacOS uses UUIDs to match up devices
				# making this sort of thing difficult and I am lazy as of this writing
		else:
			logger.error(f'Invalid callback structure formation: No device_match in item')
	return retval

async def bleak_device_dectection_callback(device, advertisement_data):
	global __lego_devices__
	global __callbacks_to_device_addresses__

	logger = logging.getLogger(__name__)

	if device:
		dev_shortname = Decoder.determine_device_shortname(advertisement_data)
		dev_systype = Decoder.determine_device_systemtype(advertisement_data)
		devclass = Decoder.classname_from_ad_data(advertisement_data)

		if devclass:
			if not device.address in __lego_devices__:
				matched_callbacks = __match_up_device(device.name, dev_systype, dev_shortname)
				if matched_callbacks:
					__lego_devices__[device.address] = devclass(advertisement_data) #BTLego.Mario(advertisement_data)

					for callback in matched_callbacks:
						if 'event_callback' in callback:
							callback_uuid = await __lego_devices__[device.address].register_callback(callback['event_callback'])
							__callbacks_to_device_addresses__[callback_uuid] = device.address

							if 'requested_events' in callback:
								for requested_event in callback['requested_events']:
									await __lego_devices__[device.address].subscribe_to_messages_on_callback(callback_uuid, requested_event)

									# You don't have to subscribe to "error" type messages...
					logger.info(f'Starting BTLE connection on {dev_shortname}')
					await __lego_devices__[device.address].connect(device)
				else:
					logger.debug(f'Device {dev_shortname} did not match any provided callbacks')

			else:
				# Reconnect if known and disconnected
				if not await __lego_devices__[device.address].is_connected():
					logger.info(f'Attempting to reconnect to {__lego_devices__[device.address].system_type}')
					await __lego_devices__[device.address].connect(device)
				else:
					pass
					# FIXME: need a TRACE level
					# logger.debug(f'Device already connected. Refusing to reconnect to {__lego_devices__[device.address].system_type}')

		else:
			# "LEGO Mario_x_y"
			# Spike prime hub starts with "LEGO Hub" but you have to pair with that, not BTLE
			if device.name and device.name.startswith("LEGO Mario"):
				if advertisement_data and advertisement_data.manufacturer_data:
					logger.warning("UNKNOWN LEGO DEVICE",dev_shortname, device.address, "RSSI:", device.rssi, advertisement_data)
				else:
					#logger.info("Found some useless Mario broadcast without the manufacturer or service UUIDs")
					pass

async def __bleak_scan_runner(duration=10):
	logger = logging.getLogger(__name__)
	global __running__

	try:
		scanner = BleakScanner(bleak_device_dectection_callback)
		logger.info("Ready to find LEGO BLE Devices!")
		logger.info("Scanning...")
		start_time = time.perf_counter()
		await scanner.start()
		while True:
			current_time = time.perf_counter()
			if current_time - start_time > duration:
				break
			if __running__ == False:
				break
			await asyncio.sleep(1)

		await scanner.stop()
		await_function_off_bleak_callback(None)
	except KeyboardInterrupt:
		print("Recieved keyboard interrupt in Bleak runner, stopping scan.")

	__running__ = False
	#print("Scan results...")
	#for d in scanner.discovered_devices:
	#	print(d)

async def __drain_off_bleak_callback_calls():
	global __running__
	logger = logging.getLogger(__name__)

	try:
		while __running__ == True:
			while not __off_bleak_callback_queue__.empty():
				fpair = __off_bleak_callback_queue__.get()
				if not fpair:
					__running__ = False
				else:
					thisloop = asyncio.get_running_loop()
					if thisloop:
						if thisloop.is_running():
							# logger.debug(f'DRAINING OFF-CALLBACKS {fpair}')
							await asyncio.create_task(fpair)
			await asyncio.sleep(0.1)
	except KeyboardInterrupt:
		print("Recieved keyboard interrupt, stopping callback function drain...")
	__running__ = False

async def __mainloop(run_second_duration):
	global __running__
	__running__ = True
	await asyncio.gather(
		__bleak_scan_runner(run_second_duration),
		__drain_off_bleak_callback_calls()
	)
	__running__ = False

def async_run(run_second_duration):
	logger = logging.getLogger(__name__)

	start_time = time.perf_counter()
	try:
		asyncio.run(__mainloop(run_second_duration))
	except KeyboardInterrupt:
		print("Recieved keyboard interrupt, stopping.")
	except asyncio.InvalidStateError:
		print("ERROR: Invalid state in Bluetooth stack, we're done here...")
	stop_time = time.perf_counter()

	if len(__lego_devices__):
		logger.info(f'Done with LEGO BLE session after {int(stop_time - start_time)} seconds...')
		for device_address in __lego_devices__:
			asyncio.run(__lego_devices__[device_address].disconnect())
	else:
		logger.info("Didn't connect to a LEGO Device.  Quitting.")
