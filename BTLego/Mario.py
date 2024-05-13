import asyncio
import logging
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder
from .MarioScanspace import MarioScanspace

class Mario(BLE_Device):

	# MESSAGE TYPES ( type, key, value )
	# event:
	#	'button':			'pressed'
	#	'consciousness':	'asleep','awake'
	#	'coincount':		(count_int, last_obtained_via_int)
	#	'power':			'turned_off'
	#	'bt':				'disconnected'
	#	'multiplayer':		('coincount', count), ('double_coincount', count),  ('triple_coincount', count)
	# motion
	#	TODO raw data
	#	TODO gesture
	# scanner
	#	'code':		((5-char string),(int))
	#	'color':	(solid_colors)
	# pants
	#	'pants': (pants_codes)
	# info
	#	'player':		'mario', 'luigi', 'peach'
	#	'icon': 		((app_icon_names),(app_icon_color_names))
	#	'batt':			(percentage)
	#	'power': 		'turning_off', 'disconnecting'
	# voltage:
	#	TODO
	# error
	#	message:	(str)

	device_property_exclusion_str = (
	)

	# Set in the advertising name
	app_icon_names = {
		0x61: 'flag',		# a
		0x62: 'bell',		# b
		0x63: 'coin',		# c
		0x64: 'fireflower',	# d
		0x65: 'hammer',		# e
		0x66: 'heart',		# f
		0x67: 'mushroom',	# g
		0x68: 'p-switch',	# h
		0x69: 'pow',		# i
		0x6a: 'propeller',	# j
		0x6b: 'star'		# k
	}
	app_icon_ints = {}

	app_icon_color_names = {
		0x72: 'red',	# r
		0x79: 'yellow', # y
		0x62: 'blue',   # b
		0x67: 'green'   # g
	}
	app_icon_color_ints = {}

	# reverse map some dicts so you can index them either way
	app_icon_ints = dict(map(reversed, app_icon_names.items()))
	app_icon_color_ints = dict(map(reversed, app_icon_color_names.items()))

	def __init__(self,advertisement_data=None):
		super().__init__(advertisement_data)

		if self.system_type == 'mario':
			self.part_identifier = "mar0007"
		elif self.system_type == 'luigi':
			self.part_identifier = "mar0062"
		elif self.system_type == 'peach':
			self.part_identifier = "mar0112"

		self.mode_probe_ignored_info_types = ( 0x7, 0x8 )	# Doesn't support motor bias or capability bits

		# Mario defaults to this
		self.volume = 100

	# Override
	def _decode_property(self, prop_id, prop_value):

		if Decoder.hub_property_str[prop_id] == 'Advertising Name':
			name = prop_value
			#LEGO Mario_j_r

			if name.startswith("LEGO Mario_") == False or len(name) != 14:
				# print(name.encode("utf-8").hex())
				# Four spaces after the name
				if name == "LEGO Peach    ":
					self.message_queue.put( ('info', 'peach', 'no_icon_or_color') )
					self.logger.info("Peach has no icon or color set")
				elif name == "LEGO Mario    ":
					self.message_queue.put( ('info', 'mario', 'no_icon_or_color') )
				elif name == "LEGO Luigi    ":
					self.message_queue.put( ('info', 'luigi', 'no_icon_or_color') )
				else:
					self.message_queue.put( ('info', 'unknown', f'Unusual advertising name set:\"{name}\"') )
				return

			icon = ord(name[11])
			color = ord(name[13])

			if not icon in Mario.app_icon_names:
				self.logger.info("Unknown icon:"+str(hex(icon)))
				self.message_queue.put( ('info', 'unknown', f'Icon {hex(icon)} not found:{name[11]}') )
				return

			if not color in Mario.app_icon_color_names:
				self.message_queue.put( ('info', 'unknown', f'Icon {hex(color)} color not found:{name[13]}') )
				return

			if self.logger.isEnabledFor(logging.DEBUG):
				color_str = Mario.app_icon_color_names[color]
				icon_str = Mario.app_icon_names[icon]
				self.message_queue.put( ('info', 'debug_icon', (color_str, icon_str )) )

			self.message_queue.put(('info','icon',(icon,color)))

		elif Decoder.hub_property_str[prop_id] == 'Mario Volume':
			# hat tip to https://github.com/djipko/legomario.py/blob/master/legomario.py
			self.message_queue.put(('info','volume',prop_value))
			self.volume = prop_value

	# ---- Bluetooth port writes ----

	async def set_icon(self, icon, color):
		if icon not in Mario.app_icon_ints:
			self.logger.error("ERROR: Attempted to set invalid icon:"+icon)
			return
		if color not in Mario.app_icon_color_ints:
			self.logger.error("ERROR: Attempted to set invalid color for icon:"+color)

		set_name_bytes = bytearray([
			0x00,	# len placeholder
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x1,	# 'Advertising Name'
			0x1		# 'Set'
		])

		set_name_bytes = set_name_bytes + "LEGO Mario_I_C".encode()

		set_name_bytes[0] = len(set_name_bytes)
		set_name_bytes[16] = Mario.app_icon_ints[icon]
		set_name_bytes[18] = Mario.app_icon_color_ints[color]

		# FIXME: How about use this instead?
		#self.send_property_message(Decoder.hub_property_int['Advertising Name'], name_only_but_bytearray):

		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, set_name_bytes)
		await asyncio.sleep(0.1)

	async def erase_icon(self):
		if self.system_type != 'peach':
			# FIXME: Ok, well, how about you erase somebody else and figure this out
			self.logger.error("ERROR: Don't know how to erase any player except peach")
			return

		set_name_bytes = bytearray([
			0x00,	# len placeholder
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x1,	# 'Advertising Name'
			0x1		# 'Set'
		])

		set_name_bytes = set_name_bytes + "LEGO Peach    ".encode()

		set_name_bytes[0] = len(set_name_bytes)

		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, set_name_bytes)
		await asyncio.sleep(0.1)
