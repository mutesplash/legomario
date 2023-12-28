import asyncio
from enum import IntEnum
from ..Decoder import Decoder

import importlib
from os.path import dirname, basename, isfile, join
import glob

class Devtype(IntEnum):
#	PROPERTY = 0
	FIXED = 1
	LPF = 2

def generate_valid_lpf_message_types():
	modules = glob.glob(join(dirname('BTLego/LPF_Devices/'), "*.py"))
	modules.sort()
	class_objects = []
	for i, f in list(enumerate(modules)):
		b = basename(f)[:-3]
		if isfile(f) and not f.endswith('__init__.py'):
			lpf_classname = basename(f)[:-3]
			lpf_class_module = importlib.import_module(f'BTLego.LPF_Devices.{lpf_classname}')
			lpf_classobj = getattr(lpf_class_module, lpf_classname)
			if issubclass(lpf_classobj, LPF_Device):
				class_objects.append(lpf_classobj)
			else:
				modules.remove(f)	# Not a LPF_Device
		else:
			modules.remove(f)	# First order filter

	valid_message_types = set()
	for lpf_classobj in class_objects:
		theclass = lpf_classobj(-1)
		lpf_message_types = theclass.message_types
		if lpf_message_types:
			for t in lpf_message_types: valid_message_types.add(t)

	return list(valid_message_types)

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class LPF_Device():

	generated_message_types = ( )

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.FIXED

		self.port = port
		self.name = ''		# Decoder.io_type_id_str[self.port_id]
		self.port_id = 0x0	# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x0	# Decoder.io_event_type_str[0x1]
		self.delta_interval = 5

		self.hw_ver_str = None
		self.fw_ver_str = None

		self.mode_subs = {
			# mode_number: ( delta_interval, subscribe_boolean ) or None
		}

		self.generated_message_types = ( )

		# Don't need to index by self.device_ports[port_id] anymore?
		# Index: Port Type per Decoder.io_type_id_str index, value: attached hardware port identifier (int or tuple)

	@property
	def message_types(self):
		return self.generated_message_types

	def set_subscribe(self, message_type, should_subscribe):
		return False

	def send_message(self, message):
		# ( action, (parameters,) )
		return None

	# Decode Port Value - Single
	def decode_pvs(self, port, data):
		return None

	def PIFSetup_data_for_message_type(self, message_type):
		# PIFS: Port Input Format Setup.  Everything you need to set this bluetooth command in Section 3.17.1
		# return 4-item array [port, mode, delta interval, subscribe on/off]
		# Base class returns nothing
		# FIXME: use abc
		return None

	# FIXME: single message type could result in multiple modes needed to subscribe, currently returns bytearray()
	def gatt_payload_for_subscribe(self, message_type, should_subscribe):
		# Return the bluetooth payload to be sent via GATT write to perform the selected subscription operation
		return None

