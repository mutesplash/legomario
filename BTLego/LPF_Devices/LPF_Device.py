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
		# If you let this thing import itself,
		if isfile(f) and not f.endswith('__init__.py'):
			lpf_classname = basename(f)[:-3]
			if lpf_classname != 'LPF_Device':
				lpf_class_module = importlib.import_module(f'BTLego.LPF_Devices.{lpf_classname}')
				lpf_classobj = getattr(lpf_class_module, lpf_classname)
				if issubclass(lpf_classobj, LPF_Device):
					class_objects.append(lpf_classobj)
				else:
					modules.remove(f)	# Not a LPF_Device
			else:
				# Do not do this to yourself, LPF_Device, because accessing
				# LPF_Device.message_types assigns generated_message_types to
				# the not-None value of [] and then every subsequent class in
				# this list will pick the not-None value up from its parent class (this one)
				# and refuse to populate
				#
				# We can thank issubclass() for thinking a class is its own
				# subclass for this now-fixed bug...
				modules.remove(f)
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

	generated_message_types = None

	def __init__(self, port=-1):
		# Port number the device is attached to on the BLE Device

		self.devtype = Devtype.FIXED

		self.port = port
		self.name = ''		# Decoder.io_type_id_str[self.port_id]
		self.port_id = 0x0	# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str
		self.status = 0x1	# Decoder.io_event_type_str[0x1]
		self.delta_interval = 5

		# This is the currently "negatively selected" mode for operating
		# Many devices won't accept input to modes unless it's "selected" by
		# disabling notifications on the mode
		self._selected_mode = -1

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.hw_ver_str = None
		self.fw_ver_str = None

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
		}

	@property
	def message_types(self):

		lpf_class_module = importlib.import_module(f'BTLego.LPF_Devices.{self.__class__.__name__}')
		lpf_classobj = getattr(lpf_class_module, self.__class__.__name__)

		if lpf_classobj.generated_message_types is None:
			generated_array = []
			for mode,config in self.mode_subs.items():
				if config[3]:
					generated_array.extend(config[3])
			lpf_classobj.generated_message_types = tuple(generated_array)
			if not lpf_classobj.generated_message_types:
				lpf_classobj.generated_message_types = []
		return lpf_classobj.generated_message_types

	async def send_message(self, message, gatt_payload_writer):
		# ( action, (parameters,) )
		return False

	# Decode Port Value - Single
	def decode_pvs(self, port, data):
		return None

	async def subscribe_to_messages(self, message_type, should_subscribe, gatt_payload_writer):
		if message_type in self.generated_message_types:
			subbed_anything = False
			for mode_int in self.mode_subs:
				if message_type in self.mode_subs[mode_int][3]:
					sub_result = await self.PIF_single_setup(mode_int, should_subscribe, gatt_payload_writer)
					if not subbed_anything:
						subbed_anything = sub_result
			return subbed_anything
		return False

	# Section 3.23.1
	# FIXME: Can't change the deltas from defaults
	# Mostly used to set/unset subscription options for modes (notification disable/enable)

	# Several devices can be subscribed, but do not return any useful data (RGB, DT_Beeper).
	# Instead, the usefulness of subscribing is to send the Port Input Format in the
	# negative (for subscription) which switches the operating mode of the device:
	# It only operates in one mode at a time and won't switch just by sending a different
	# command.
	# ( I guess because it has to prepare a buffer since the sizes vary? )

	async def PIF_single_setup(self, mode, should_subscribe, gatt_payload_writer):
		if not mode in self.mode_subs:
			return False

		payload = bytearray([
			0x0A,		# length
			0x00,
			0x41,		# Port input format (single)
			self.port,	# port
			mode,
		])

		# delta interval (uint32)
		# 5 is what was suggested by https://github.com/salendron/pyLegoMario
		delta_int = self.mode_subs[mode][0]

		payload.extend(delta_int.to_bytes(4,byteorder='little',signed=False))

		if should_subscribe:
			payload.append(0x1)		# notification enable
			self.mode_subs[mode][1] = True
		else:
			payload.append(0x0)		# notification disable
			self.mode_subs[mode][1] = False
		#print(" ".join(hex(n) for n in payload))

		payload[0] = len(payload)
		return await gatt_payload_writer(payload)

	# This does the "negative subscribe" to select the device's mode
	async def select_mode_if_not_selected(self, mode, gatt_payload_writer):
		if mode != self._selected_mode:
			self._selected_mode = mode
			await self.PIF_single_setup(mode, False, gatt_payload_writer)
