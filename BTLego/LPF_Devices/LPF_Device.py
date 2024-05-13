import asyncio
from enum import IntEnum
from queue import SimpleQueue

from ..Decoder import Decoder

import importlib
from os.path import dirname, basename, isfile, join
import glob

class Devtype(IntEnum):
#	PROPERTY = 0
	FIXED = 1
	LPF = 2

def generate_valid_lpf_message_types():
	"""
	Iterate over all LPF2 devices and get their list of emitted messages types
	that correspond to integer modes by calling message_types() on their instances.

	BLE_Device calls this so it can validate subscription requests
	"""
	modules = glob.glob(join(dirname('BTLego/LPF_Devices/'), "*.py"))
	modules.sort()
	class_objects = []
	for i, f in list(enumerate(modules)):
		b = basename(f)[:-3]
		# If you let this thing import itself,
		if isfile(f) and not f.endswith('__init__.py'):
			lpf_classname = basename(f)[:-3]
			if not lpf_classname.startswith('LPF_'):
				# All intermediate subclasses need to start with LPF_ to avoid similar problems
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
		#print(f'Generating {lpf_classobj.__name__}...')
		lpf_message_types = theclass.message_types
		#print(f'\t{lpf_message_types}')
		if lpf_message_types:
			for t in lpf_message_types: valid_message_types.add(t)
	return list(valid_message_types)

class LPF_Device():

	generated_message_types = None

	# These devices will not freak out if you ask them their motor bias when asking
	# the port's mode information (provided the BLE_Device will accept your request)
	#
	# Ok this is slightly overstating it, since Hub4 seems to be the only thing
	# capable of doing this (All its internal devices respond to it)
	motor_bias_device_allowlist = [ 0x1, 0x2, 0x20, 0x22, 0x26, 0x2e, 0x30, 0x31, 0x41, 0x4b, 0x4c ]

	def __init__(self, port=-1):
		"""
		port:
			Port number the device is attached to on the BLE Device

		Built-in devices seem to follow similar rules to LPF2 devices, so FIXED
		vs LPF is mostly to be able to determine if a device could possibly
		disappear

		All intermediate subclasses need to start with LPF_
		"""

		self.devtype = Devtype.FIXED

		self.part_identifier = None

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

		self.outstanding_requests = SimpleQueue()

		# Probed count
		self.mode_count = -1	# Default unprobed

		self.hw_ver_str = None
		self.fw_ver_str = None

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
		}

	@property
	def message_types(self):
		"""
		Iterate mode_subs to determine what message types this class emits and
		return it as a tuple
		"""

		lpf_class_module = importlib.import_module(f'BTLego.LPF_Devices.{self.__class__.__name__}')
		lpf_classobj = getattr(lpf_class_module, self.__class__.__name__)

		if lpf_classobj.generated_message_types is None:
			generated_array = []
			for mode,config in self.mode_subs.items():
				if config[3]:
					generated_array.extend(config[3])
			lpf_classobj.generated_message_types = tuple(generated_array)
			if not lpf_classobj.generated_message_types:
				lpf_classobj.generated_message_types = ()
		return lpf_classobj.generated_message_types

	async def send_message(self, message, gatt_payload_writer):
		"""
		gatt_payload_writer:
			This should be the lambda from BLE_device class that owns this device
			that accepts a bytearray to write to the BLE connection
		"""

		action = message[0]
		parameters = message[1]

		if action == 'delta_set':
			mode, delta_interval = parameters
			return await self.set_mode_delta(mode, delta_interval)

		# ( action, (parameters,) )
		return False

	def decode_pvs(self, port, data):
		"""
		Decode Port Value - Single
		LWP 3.21
		A BLE_device instance should call this after receiving data generated by
		the device this class instance represents

		Return (type, key, value) suitable for client processing

		This stub just dumps the data out and indicates a subclass should override
		"""

		print(f'{self.name} PORT {port} LPF_DATA: '+' '.join(hex(n) for n in data))
		return None

	async def get_port_info(self, mode, gatt_payload_writer):
		"""
		This function does a (negative) select on the provided mode
		and then Port Info Request (0x21)
		LWP Section 3.15.2

		Information Type 0: Request port_value_single value
		"""

		await self.select_mode_if_not_selected(mode, gatt_payload_writer)

		information_type = 0
		payload = bytearray([
			0x5,	# len
			0x0,	# padding
			0x21,	# Command: port_info_req
			# end header
			self.port,
			information_type
		])
		payload[0] = len(payload)

		results = await gatt_payload_writer(payload)

		# Yeah, even doing this, seems very race condition-y
		self.outstanding_requests.put(mode)
		return results

	async def subscribe_to_messages(self, message_type, should_subscribe, gatt_payload_writer):
		"""
		Request the device emit or stop returning message_type tuples by setting
		the port's mode information format.

		These correspond to modes in the device's mode_subs dictionary
		"""
		if self.generated_message_types:
			if message_type in self.generated_message_types:
				subbed_anything = False
				for mode_int in self.mode_subs:
					if message_type in self.mode_subs[mode_int][3]:
						sub_result = await self.PIF_single_setup(mode_int, should_subscribe, gatt_payload_writer)
						if not subbed_anything:
							subbed_anything = sub_result
				return subbed_anything
		return False

	async def set_mode_delta(self, mode, delta_interval):
		"""
		Set the numerical limit of change in the value of the specified mode that
		is necessary to cause the device to report a value.

		For example, Controller_Buttons are discrete, so a delta of anything
		other than zero will cause the device to only report buttons that have a
		raw value greater the delta value of the last button or zero, which is
		why to get all the button messages, the delta needs to be zero to report
		all changes

		For twitchy devices like gyroscopes, setting the delta to 5 will cut down
		on the volume of messages from the device.

		For some devices (such as Controller_Buttons) setting it to zero only
		shows changes to the current value.  For other devices, zero will constantly
		emit values, even if they have not changed (because the delta between the
		values is zero)

		Sometimes changing this from the defaults breaks the device.  Check the notes!
		FIXME: WHAT NOTES!?
		"""
		if not mode in self.mode_subs:
			return False

		self.mode_subs[mode][0] = delta_interval

		if mode == self._selected_mode:
			return await self.PIF_single_setup(mode, self.mode_subs[mode][1], gatt_payload_writer)
		return True

	async def PIF_single_setup(self, mode, should_subscribe, gatt_payload_writer):
		"""
		Port Input Format (PIF) Setup for a single port (versus a combination of ports)
		LWP Section 3.23.1

		Sets the subscription and delta, previously set with set_mode_delta(),
		to use for the data returned for the mode

		LWP Documentation calls (un)subscribing to port data as notification disable/enable

		Several devices can be subscribed that are not supposed to return data
		according to their port mode information, but do not return any useful
		data (RGB, DT_Beeper).

		"""
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

		self._selected_mode = mode

		return await gatt_payload_writer(payload)

	async def select_mode_if_not_selected(self, mode, gatt_payload_writer):
		'''
		This does the "negative subscribe" to select the device's mode,
		unless it's already selected

		WHY do a negative select?  Many devices do not like to have data written
		to them that specifies a port to be written to that is did not previously
		receive a subscription command.  If this data is not of constant interest
		(in this case, not already subscribed) or the mode is an output-only mode,
		a negative selection will suffice.

		A negative select effectively changes the current operating mode of the
		device, perhaps because different buffers need to be prepared
		'''
		if mode != self._selected_mode:
			await self.PIF_single_setup(mode, False, gatt_payload_writer)
