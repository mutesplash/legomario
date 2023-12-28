import asyncio
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder

class Hub2(BLE_Device):
	# 0:	Don't debug
	# 1:	Print weird stuff
	# 2:	Print most of the information flow
	# 3:	Print stuff even you the debugger probably don't need
	DEBUG = 0

	# Now wait a second, what message are you getting from the rgb?
# 	message_types = (
# 		'hub2_rgb',
# 		'rgb_i',		# Ok this is a problem: Can't sub to devices dynamically NOPE, FIXED THAT
# 	)

	def __init__(self,advertisement_data=None, json_code_dict=None):
		super().__init__(advertisement_data)

		self.mode_probe_ignored_info_types = ( 0x7, 0x8 )	# Doesn't support motor bias or capability bits
			# FIXME: HOWEVER, I haven't attached a really, really dumb LPF2 motor to it: ie 0x1 or something, so MAYBE

# hub_2 Attached Current on port 59
# 	Draining for: hub_attached_io - port 59 attached IOTypeID:21 hw:v1.0.0.0 sw:v1.0.0.0
# hub_2 Attached Voltage on port 60
# 	Draining for: hub_attached_io - port 60 attached IOTypeID:20 hw:v1.0.0.0 sw:v1.0.0.0

# Oh look it's a duplicate device like I predicted I would have to deal with!  Shock!

# hub_2 Attached Powered Up hub IMU temperature on port 61
# 	Draining for: hub_attached_io - port 61 attached IOTypeID:60 hw:v1.0.0.0 sw:v1.0.0.0
# hub_2 Attached Powered Up hub IMU temperature on port 96
# 	Draining for: hub_attached_io - port 96 attached IOTypeID:60 hw:v0.0.0.1 sw:v0.0.0.1

# hub_2 Attached Powered Up hub IMU accelerometer on port 97
# 	Draining for: hub_attached_io - port 97 attached IOTypeID:57 hw:v0.0.0.1 sw:v0.0.0.1
# hub_2 Attached Powered Up hub IMU gyro on port 98
# 	Draining for: hub_attached_io - port 98 attached IOTypeID:58 hw:v0.0.0.1 sw:v0.0.0.1

# hub_2 Attached Powered Up hub IMU position on port 99
# 	Draining for: hub_attached_io - port 99 attached IOTypeID:59 hw:v0.0.0.1 sw:v0.0.0.1

# hub_2 Attached Powered Up hub IMU gesture on port 100
# 	Draining for: hub_attached_io - port 100 attached IOTypeID:54 hw:v0.0.0.1 sw:v0.0.0.1

	# ---- Make data useful ----

	# ---- Random stuff ----

	def dp(pstr, level=1):
		if Hub2.DEBUG:
			if Hub2.DEBUG >= level:
				print(pstr)

	# ---- Bluetooth port writes ----
