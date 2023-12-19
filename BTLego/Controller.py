import asyncio
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder

from .LPF_Devices.HP_Button import Button
from .LPF_Devices.HP_AdName import AdName
from .LPF_Devices.HP_RSSI import RSSI

class Controller(BLE_Device):
	# 0:	Don't debug
	# 1:	Print weird stuff
	# 2:	Print most of the information flow
	# 3:	Print stuff even you the debugger probably don't need
	DEBUG = 0

	device_has_properties = (
		Button,
		AdName,
		RSSI
	)

	def __init__(self,advertisement_data=None, json_code_dict=None):
		super().__init__(advertisement_data)

		self.mode_probe_ignored_info_types = ( 0x7, )	# Doesn't support motor bias

	# ---- Random stuff ----

	def dp(pstr, level=1):
		if Controller.DEBUG:
			if Controller.DEBUG >= level:
				print(pstr)
