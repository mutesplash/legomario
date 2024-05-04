import logging
import asyncio

import BTLego
from BTLego.MarioScanspace import MarioScanspace

#BTLego.setLoggingLevel(logging.DEBUG)

async def mariocallbacks(message):
	( cb_uuid, message_type, message_key, message_value ) = message

	logger = logging.getLogger(BTLego.__name__)
	logger.debug("CALLBACK:"+str(message))
	mario_device = BTLego.device_for_callback_id(cb_uuid)

	if message_type == 'scanner':
		if message_key == 'code':
			code_info = MarioScanspace.get_code_info(message_value[1])
			print("Scanned "+code_info['label'])

	if message_type == 'event' and message_key == 'coincount':
		coincount, coinsource = message_value
		print(f'Now have {coincount} coins total from {MarioScanspace.event_scanner_coinsource[coinsource]}')

# You only need one of these for this example, but here's how to use three
# different types of matching to register the callback to the device you want to use
callback_matcher = [
	{
		# 'AnyMario' matches whatever it can find.
		# This may not be what you want to happen if you have more than one!
		'device_match': [ 'AnyMario' ],
		'event_callback': mariocallbacks,
		'requested_events': [ 'event', 'scanner' ]
	}
#	,{
		# Match a specific type of device by the name given in BTLego.Decoder.advertised_system_type
#		'device_match': [ 'Mario', 'Peach', 'Luigi' ],
#		'event_callback': mariocallbacks,
#		'requested_events': [ 'event', 'scanner' ]
#	},

#	,{
		# Match the advertised name
#		'device_match': [ 'LEGO Mario_a_r' ],
#		'event_callback': mariocallbacks,
#		'requested_events': [ 'event', 'scanner' ]
#	}

]
BTLego.set_callbacks(callback_matcher)

json_code_file = "../mariocodes.json"
if not MarioScanspace.import_codefile(json_code_file):
	print(f'Known code database ({json_code_file}) NOT loaded!')

# If you want more control, just copy & modify the detection callback system out
# of BTLego/__init__.py that instantiates the BLE_Device, registers the callback,
# subscribes to messages, and connect()s it
run_seconds = 60
BTLego.async_run(run_seconds)
