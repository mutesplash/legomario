import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

class Force(LPF_Device):

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.LPF

		self.port = port

		self.port_id = 0x3f
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
			0: ( 5, False),		# FORCE
			1: ( 5, False),		# TOUCH
			2: ( 5, False),		# TAP
			3: ( 5, False),		# FPEAK
			4: ( 5, False),		# FRAW
			5: ( 5, False),		# FPRAW
		}

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)