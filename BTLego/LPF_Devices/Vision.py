import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Vision(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.LPF

		self.port = port

		self.port_id = 0x25
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 5, False),		# COLOR
			1: ( 5, False),		# PROX
			2: ( 5, False),		# COUNT
			3: ( 5, False),		# REFLT
			4: ( 5, False),		# AMBI
			5: ( 5, False),		# COL O
			6: ( 5, False),		# RGB I
			7: ( 5, False),		# IR Tx
			9: ( 5, False),		# DEBUG
			10: ( 5, False),	# CALIB
		}

#    "3": {
#         "mode_count": 11,
#         "name": "Vision Sensor",
#         "0": {
#             "direction": "IN",
#             "name": "COLOR",
#             "raw": {
#                 "min": 0.0,
#                 "max": 10.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 10.0
#             },
#             "symbol": "IDX",
#             "mapping_readable": "port_mode_info - port 3 mode 0 infotype: MAPPING  Mapping:0xc4 0x0",
#             "value_readable": " 1 8bit datasets with 3 total figures and 0 decimals"
#         },
#         "1": {
#             "direction": "IN",
#             "name": "PROX",
#             "raw": {
#                 "min": 0.0,
#                 "max": 10.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 10.0
#             },
#             "symbol": "DIS",
#             "mapping_readable": "port_mode_info - port 3 mode 1 infotype: MAPPING  Mapping:0x50 0x0",
#             "value_readable": " 1 8bit datasets with 3 total figures and 0 decimals"
#         },
#         "2": {
#             "direction": "IN",
#             "name": "COUNT",
#             "raw": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "symbol": "CNT",
#             "mapping_readable": "port_mode_info - port 3 mode 2 infotype: MAPPING  Mapping:0x8 0x0",
#             "value_readable": " 1 32bit datasets with 4 total figures and 0 decimals"
#         },
#         "3": {
#             "direction": "IN",
#             "name": "REFLT",
#             "raw": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "symbol": "PCT",
#             "mapping_readable": "port_mode_info - port 3 mode 3 infotype: MAPPING  Mapping:0x10 0x0",
#             "value_readable": " 1 8bit datasets with 3 total figures and 0 decimals"
#         },
#         "4": {
#             "direction": "IN",
#             "name": "AMBI",
#             "raw": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "symbol": "PCT",
#             "mapping_readable": "port_mode_info - port 3 mode 4 infotype: MAPPING  Mapping:0x10 0x0",
#             "value_readable": " 1 8bit datasets with 3 total figures and 0 decimals"
#         },
#         "5": {
#             "direction": "OUT",
#             "name": "COL O",
#             "raw": {
#                 "min": 0.0,
#                 "max": 10.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 10.0
#             },
#             "symbol": "IDX",
#             "mapping_readable": "port_mode_info - port 3 mode 5 infotype: MAPPING  Mapping:0x0 0x4",
#             "value_readable": " 1 8bit datasets with 3 total figures and 0 decimals"
#         },
#         "6": {
#             "direction": "IN",
#             "name": "RGB I",
#             "raw": {
#                 "min": 0.0,
#                 "max": 1023.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 1023.0
#             },
#             "symbol": "RAW",
#             "mapping_readable": "port_mode_info - port 3 mode 6 infotype: MAPPING  Mapping:0x10 0x0",
#             "value_readable": " 3 16bit datasets with 5 total figures and 0 decimals"
#         },
#         "7": {
#             "direction": "OUT",
#             "name": "IR Tx",
#             "raw": {
#                 "min": 0.0,
#                 "max": 65535.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 65535.0
#             },
#             "symbol": "N/A",
#             "mapping_readable": "port_mode_info - port 3 mode 7 infotype: MAPPING  Mapping:0x0 0x4",
#             "value_readable": " 1 16bit datasets with 5 total figures and 0 decimals"
#         }
#         "9": {
#             "direction": "IN",
#             "name": "DEBUG",
#             "raw": {
#                 "min": 0.0,
#                 "max": 1023.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 10.0
#             },
#             "symbol": "N/A",
#             "mapping_readable": "port_mode_info - port 3 mode 9 infotype: MAPPING  Mapping:0x10 0x0",
#             "value_readable": " 2 16bit datasets with 5 total figures and 0 decimals"
#         },
#         "10": {
#             "direction": "IN",
#             "name": "CALIB",
#             "raw": {
#                 "min": 0.0,
#                 "max": 65535.0
#             },
#             "pct": {
#                 "min": 0.0,
#                 "max": 100.0
#             },
#             "si": {
#                 "min": 0.0,
#                 "max": 65535.0
#             },
#             "symbol": "N/A",
#             "mapping_readable": "port_mode_info - port 3 mode 10 infotype: MAPPING  Mapping:0x10 0x0",
#             "value_readable": " 8 16bit datasets with 5 total figures and 0 decimals"
#         },
