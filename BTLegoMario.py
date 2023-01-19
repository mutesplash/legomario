import asyncio
import uuid
from queue import SimpleQueue
from collections.abc import Iterable

from bleak import BleakClient
from BTLego import BTLego

#{
#    kCBAdvDataChannel = 37;
#    kCBAdvDataIsConnectable = 1;
#    kCBAdvDataManufacturerData = {length = 8, bytes = 0x9703004403ffff00};
#    kCBAdvDataServiceUUIDs =     (
#        "00001623-1212-EFDE-1623-785FEABCD123"
#    );
#}

# https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#document-2-Advertising
# 97 03 00 44 03 ff ff 00
# Must have stripped the length and data type name off?
# 97 03 is backwards because it's supposed to be a 16 bit int
# Button state is zero
# Hub type: 44 (Luigi)
#	0x44
#	010 00100
#     2     4
#	0x43
#	010 00011
#     2     3
# 2: LEGO System
# 3&4: mario... what about the Mindstorms hub?
# Device Capabilities: 3 (Supports central and peripheral (bitmask))
# Rest is garbage, AFAIAC

# Should be BTLELegoMario but that's obnoxious
class BTLegoMario(BTLego):
	# 0:	Don't debug
	# 1:	Print weird stuff
	# 2:	Print most of the information flow
	# 3:	Print stuff even you the debugger probably don't need
	# 4:	Why did you even put this level in?
	DEBUG = 0

	which_player = None
	address = None
	lock = None
	client = None
	connected = False

	# keep around for whatever
	device = None
	advertisement = None

	# MESSAGE TYPES ( type, key, value )
	# event:
	#	'button':			'pressed'
	#	'consciousness':	'asleep','awake'
	#	'coincount':		(count_int, last_obtained_via_int)
	#	'power':			'turned_off'
	#	'bt':				'disconnected'
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
	message_queue = None

	callbacks = None
	message_types = (
		'event',
		'motion',
		'gesture',
		'scanner',
		'pants',
		'info',
		'error'
	)

	characteristic_uuid = '00001624-1212-efde-1623-785feabcd123'
	hub_service_uuid = '00001623-1212-efde-1623-785feabcd123'

	# https://github.com/bricklife/LEGO-Mario-Reveng
	IMU_PORT = 0		# Inertial Motion Unit?
						# Pybricks calls this IMU
		# Mode 0: RAW
		# Mode 1: GEST (probably more useful)
	RGB_PORT = 1
		# Mode 0: TAG
		# Mode 1: RGB
	PANTS_PORT = 2
		# Mode 0: PANT
	EVENTS_PORT = 3
		# Mode 0: CHAL
		# Mode 1: VERS
		# Mode 2: EVENTS
		# Mode 3: DEBUG
	ALT_EVENTS_PORT = 4
		# Mode 0: Events
			# More different events?
	VOLTS_PORT = 6		# Constant stream of confusing data
		# Mode 0: VLT L
		# Mode 1: VLT S

	port_name = {
		0:'IMU',
		1:'scanner',
		2:'pants',
		3:'events',
		4:'alt_events',
		6:'volts'
	}

	# populated in __init__
	port_data = {
	}

	code_data = None
	gr_codespace = {}
	br_codespace = {}
	# Color scanner is a bit buggy.  Blue works better in latest firmware, but sometimes the scanner doesn't return color messages
	solid_colors = {
		19:'white',		# Official Lego color ID for white is 1 and 19 for Light Brown (probably too close to Medium Nougat)
		21:'red',		# Bright Red
		23:'blue',		# Bright Blue
		24:'yellow',	# Bright Yellow
		26:'black',		# Black
		37:'green',		# Bright Green
		106:'orange',	# Bright Orange (listed as 'brown' elsewhere)
		119:'lime',		# Bright Yellowish Green
		221:'pink',		# Bright Purple
		268:'purple',	# Medium Lilac
		312:'nougat',	# Medium Nougat
		322:'cyan',		# Medium Azur
		324:'lavender'	# Medium Lavender
	}

	# Read the pins facing you with MSB on the left (Mario's right)
	# Some pants codes simply do not register.  May be some debouncing or max pin-down circuitry
	pants_codes = {
		0x0:'no',			# 000 000	Sometimes mario registers 0x2 as no pants, might be a pin problem?
		0x1:'vacuum',		# 000 001	Poltergust
		0x2:'no',			# 000 010	Just cover the case and pretend it's normal, who wants to get weird messages and debug them. When you actually PUSH pin 1 (0x2), you get the update icon
		0x3:'bee',			# 000 011	Acts strange and won't send messages when these pants are on.  Needs more testing
#		0x4:'?4?',			# 000 100
		0x5:'luigi',		# 000 101
		0x6:'frog',			# 000 110
							# 000 111
#		0x8:'?8?',			# 001 000	does nothing and doesn't trigger the update icon, perhaps a hidden trigger?  Might also be poltergust?
		0x9:'vacuum_button',# 001 001	Poltergust. Seems to not matter which one is the toggle!
		0xa:'tanooki',		# 001 010	Leaf icon
							# 001 011
		0xc:'propeller',	# 001 100
#		0xd:'?13?',			# 001 101
#		0xe:'?14?',			# 001 110
#		0xf:'?15?',			# 001 111
#		0x10:'?16?',		# 010 000
		0x11:'cat',			# 010 001	Bell icon
		0x12:'fire',		# 010 010
							# 010 011
		0x14:'penguin',		# 010 100
							# 010 101
#		0x16:'22?',			# 010 110
							# 010 111
		0x18:'dress',		# 011 000
							# 011 001
#		0x1a:'26?',			# 011 010
							# 011 011
#		0x1c:'28?',			# 011 100
							# 011 101
							# 011 110
							# 011 111
		0x20:'mario',		# 100 000	Because who has time to deal with errata... doesn't seem to be the SAME pin problem,  When you actually PUSH pin 5 (0x20), you get the update icon
		0x21:'mario',		# 100 001	Mario pants.  Sometimes mario registers 0x20 as mario pants, might be a pin problem?
		0x22:'builder',		# 100 010
		0x23:'ice',			# 100 011	Ice flower icon
#		0x24:'36?',			# 100 100
#		0x25:'37?',			# 100 101
#		0x26:'38?',			# 100 110
							# 100 111
#		0x28:'40?',			# 101 000
							# 101 001
		0x2a:'cat'			# 101 010	Bell icon. Peach's cat pants
							# 101 011
#		0x2c:'44?',			# 101 100
							# 101 101
							# 101 110
							# 110 111
#		0x30:'48?',			# 110 000
							# 110 001
							# 110 010
							# 110 011
							# 110 100
							# 110 101
							# 110 110
							# 110 111
#		0x38:'?56?'			# 111 000
	}

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

	def __init__(self,json_code_dict=None):
		super().__init__()

		if not BTLegoMario.code_data:
			BTLegoMario.code_data = json_code_dict

		# reverse map some dicts so you can index them either way
		if not BTLegoMario.app_icon_ints:
			BTLegoMario.app_icon_ints = dict(map(reversed, self.app_icon_names.items()))
		if not BTLegoMario.app_icon_color_ints:
			BTLegoMario.app_icon_color_ints = dict(map(reversed, self.app_icon_color_names.items()))

		# It would be nice to dynamically init the ports when you connect
		# and not do some magic numbers here but
		# 1. They're static and
		# 2. They don't "initialize" when you connect
		self.__init_port_data(0,0x47)
		self.__init_port_data(1,0x49)
		self.__init_port_data(2,0x4A)
		self.__init_port_data(3,0x46)
		self.__init_port_data(4,0x55)
		self.__init_port_data(6,0x14)

		self.message_queue = SimpleQueue()
		self.callbacks = {}

		self.lock = asyncio.Lock()

	def __init_port_data(self, port, port_id):
		self.port_data[port] = {
			'io_type_id':port_id,
			'name':BTLego.io_type_id_str[port_id],
			'status': 0x1	# BTLego.io_event_type_str[0x1]
		}

	def which_device(advertisement_data):
		# https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#document-2-Advertising
		# kCBAdvDataManufacturerData = 0x9703004403ffff00
		# 919 aka 0x397 or the lego manufacturer id
		if 919 in advertisement_data.manufacturer_data:
			# 004403ffff00
			# 00 Button state
			# 44 System type (44 for luigi, 43 mario)
			#	0x44 010 00100	System type 010 (Lego system), Device number(IDK)
			#	0x43 010 00011
			# 03 Capabilites
			#	0000 0011
			#	       01	Central role
			#          10	Peripheral role
			# ff Last network ID (FF is not implemented)
			# ff Status (I can be everything)
			# 00 Option (unused)
			if advertisement_data.manufacturer_data[919][1] == 0x43:
				return 'mario'
			elif advertisement_data.manufacturer_data[919][1] == 0x44:
				return 'luigi'
			elif advertisement_data.manufacturer_data[919][1] == 0x45:
				return 'peach'
			else:
				BTLegoMario.dp("Detected unknown player: "+str(hex(advertisement_data.manufacturer_data[919][1])))
				return 'UNKNOWN_MARIO'
		return None

	async def connect(self, device, advertisement_data):
		async with self.lock:
			self.which_player = BTLegoMario.which_device(advertisement_data)
			BTLegoMario.dp("Connecting to "+str(self.which_player)+"...",2)
			self.device = device
			self.advertisement = advertisement_data
			try:
				async with BleakClient(device.address) as self.client:
					if not self.client.is_connected:
						BTLegoMario.dp("Failed to connect after client creation")
						return
					BTLegoMario.dp("Connected to "+self.which_player+"! ("+str(device.name)+")",2)
					self.message_queue.put(('info','player',self.which_player))
					self.connected = True
					await self.client.start_notify(BTLegoMario.characteristic_uuid, self.mario_events)
					await asyncio.sleep(0.1)

					# turn on everything everybody registered for
					for callback_uuid,callback in self.callbacks.items():
						await self.set_event_subscriptions(callback[1])

					# Not always sent on connect
					await self.request_name_update()
					# Definitely not sent on connect
					await self.request_volume_update()
					await self.request_version_update()

					while self.client.is_connected:
						await asyncio.sleep(0.05)
					self.connected = False
					BTLegoMario.dp(self.which_player+" has disconnected.",2)

			except Exception as e:
				BTLegoMario.dp("Unable to connect to "+str(device.address) + ": "+str(e))

	def register_callback(self, callback):
		# FIXME: Un-register?
		callback_uuid = str(uuid.uuid4())
		self.callbacks[callback_uuid] = (callback, ())
		return callback_uuid

	def request_update_on_callback(self,update_request):
		# FIXME: User should be able to pokes mario for stuff like request_name_update
		pass

	async def subscribe_to_messages_on_callback(self, callback_uuid, message_type, subscribe=True):
		# FIXME: Uhh, actually doesn't allow you to unsubscribe.  Good design here. Top notch
		if not message_type in self.message_types:
			BTLegoMario.dp("Invalid message type "+message_type)
			return False
		if not callback_uuid in self.callbacks:
			BTLegoMario.dp("Given UUID not registered to recieve messages "+message_type)
			return False

		do_nothing = False
		callback_settings = self.callbacks[callback_uuid]
		current_subscriptions = callback_settings[1]
		new_subscriptions = ()
		if subscribe:
			if message_type in current_subscriptions:
				do_nothing = True
			else:
				new_subscriptions = current_subscriptions+(message_type,)
		else:
			if message_type in current_subscriptions:
				sub_list = list(current_subscriptions)
				sub_list.remove(message_type)
				new_subscriptions = tuple(sub_list)
			else:
				do_nothing = True

		if do_nothing:
			new_subscriptions = current_subscriptions
		else:
			self.callbacks[callback_uuid] = (callback_settings[0], new_subscriptions)

		if self.connected:
			await self.set_event_subscriptions(new_subscriptions)

		return True

	async def set_event_subscriptions(self, current_subscriptions):
		# FIXME: Uhh, actually doesn't allow you to unsubscribe.  Good design here. Top notch
		if self.connected:
			for subscription in current_subscriptions:
				if subscription == 'event':
					await self.set_port_subscriptions([[self.EVENTS_PORT,2,True]])
					await self.set_updates_for_hub_properties([
						['Button',True]				# Works as advertised (the "button" is the bluetooth button)
					])

				elif subscription == 'motion':
					await self.set_port_subscriptions([[self.IMU_PORT,0,True]])
				elif subscription == 'gesture':
					await self.set_port_subscriptions([[self.IMU_PORT,1,True]])
				elif subscription == 'scanner':
					await self.set_port_subscriptions([[self.RGB_PORT,0,True]])
				elif subscription == 'pants':
					await self.set_port_subscriptions([[self.PANTS_PORT,0,True]])
				elif subscription == 'info':
					await self.set_updates_for_hub_properties([
						['Advertising Name',True]	# I guess this works different than requesting the update because something else could change it, but then THAT would cause an update message

						# Kind of a problem to implement in the future because you don't want these spewing at you
						# Probably need to be separate types
						#['RSSI',True],				# Doesn't really update for whatever reason
						#['Battery Voltage',True],	# Transmits updates pretty frequently
					])
#				elif subscription == 'error'
		else:
			BTLegoMario.dp("NOT CONNECTED.  Not setting port subscriptions",2)

	async def drain_messages(self):
		while not self.message_queue.empty():
			message = self.message_queue.get()
			for callback_uuid, callback in self.callbacks.items():
				if message[0] in callback[1]:
					await callback[0]((callback_uuid,) + message)

	async def mario_events(self, sender, data):

		bt_message = BTLego.decode_payload(data)
		msg_prefix = self.which_player+" "

		if bt_message['error']:
			BTLegoMario.dp(msg_prefix+"ERR:"+bt_message['readable'])
			self.message_queue.put(('error','message',bt_message['readable']))

		else:
			if BTLego.message_type_str[bt_message['type']] == 'port_input_format_single':
				if BTLegoMario.DEBUG >= 2:
					msg = "Disabled notifications on "
					if bt_message['notifications']:
						# Returned typically after gatt write
						msg = "Enabled notifications on "

					port_text = "port "+str(bt_message['port'])
					if bt_message['port'] in BTLegoMario.port_data:
						# Sometimes the hub_attached_io messages don't come in before the port subscriptions do
						port_text = BTLegoMario.port_data[bt_message['port']]['name']+" port"

					BTLegoMario.dp(msg_prefix+msg+port_text+", mode "+str(bt_message['mode']), 2)

			elif BTLego.message_type_str[bt_message['type']] == 'hub_attached_io':
				event = BTLego.io_event_type_str[bt_message['event']]
				if event == 'attached':
					dev = "UNKNOWN DEVICE"
					if bt_message['io_type_id'] in BTLego.io_type_id_str:
						dev = BTLego.io_type_id_str[bt_message['io_type_id']]
					if bt_message['port'] in self.port_data:
						BTLegoMario.dp(msg_prefix+"Re-attached "+dev+" on port "+str(bt_message['port']),2)
					else:
						BTLegoMario.dp(msg_prefix+"Attached "+dev+" on port "+str(bt_message['port']),2)

					self.port_data[bt_message['port']] = {
						'io_type_id':bt_message['io_type_id'],
						'name':dev,
						'status':bt_message['event']
					}

				elif event == 'detached':
					BTLegoMario.dp(msg_prefix+"Detached "+dev+" on port "+str(bt_message['port']),2)
					self.port_data[bt_message['port']]['status'] = 0x0 # io_event_type_str

				else:
					BTLegoMario.dp(msg_prefix+"HubAttachedIO: "+bt_message['readable'],1)

			elif BTLego.message_type_str[bt_message['type']] == 'port_value_single':
				if not bt_message['port'] in self.port_data:
					BTLegoMario.dp(msg_prefix+"ERR: Attempted to send data to unconfigured port "+str(bt_message['port']))
				else:
					pd = self.port_data[bt_message['port']]
					if pd['name'] == 'Mario Pants Sensor':
						self.decode_pants_data(bt_message['value'])
					elif pd['name'] == 'Mario RGB Scanner':
						self.decode_scanner_data(bt_message['value'])
					elif pd['name'] == 'Mario Tilt Sensor':
						self.decode_accel_data(bt_message['value'])
					elif pd['name'] == 'Mario Events':
						self.decode_event_data(bt_message['value'])
					else:
						if BTLegoMario.DEBUG >= 2:
							BTLegoMario.dp(msg_prefix+"Data on "+self.port_data[bt_message['port']]['name']+" port"+":"+" ".join(hex(n) for n in data),2)

			elif BTLego.message_type_str[bt_message['type']] == 'hub_properties':
				if not BTLego.hub_property_op_str[bt_message['operation']] == 'Update':
					# everything else is a write, so you shouldn't be getting these messages!
					BTLegoMario.dp(msg_prefix+"ERR NOT UPDATE: "+bt_message['readable'])

				else:
					if not bt_message['property'] in BTLego.hub_property_str:
						BTLegoMario.dp(msg_prefix+"Unknown property "+bt_message['readable'])
					else:
						if BTLego.hub_property_str[bt_message['property']] == 'Button':
							if bt_message['value']:
								BTLegoMario.dp(msg_prefix+"Bluetooth button pressed!",2)
								self.message_queue.put(('event','button','pressed'))
							else:
								# Well, nobody cares if it WASN'T pressed...
								pass

						# The app seems to be able to subscribe to Battery Voltage and get it sent constantly
						elif BTLego.hub_property_str[bt_message['property']] == 'Battery Voltage':
							BTLegoMario.dp(msg_prefix+"Battery is at "+str(bt_message['value'])+"%",2)
							self.message_queue.put(('info','batt',bt_message['value']))

						elif BTLego.hub_property_str[bt_message['property']] == 'Advertising Name':
							self.decode_advertising_name(bt_message['value'])

						# hat tip to https://github.com/djipko/legomario.py/blob/master/legomario.py
						elif BTLego.hub_property_str[bt_message['property']] == 'Mario Volume':
							BTLegoMario.dp(msg_prefix+"Volume set to "+str(bt_message['value']),2)
							self.message_queue.put(('info','volume',bt_message['value']))

						else:
							BTLegoMario.dp(msg_prefix+bt_message['readable'],2)

			elif BTLego.message_type_str[bt_message['type']] == 'port_output_command_feedback':
				# Don't really care about these messages?  Just a bunch of queue status reporting
				BTLegoMario.dp(msg_prefix+" "+bt_message['readable'],3)
				pass

			elif BTLego.message_type_str[bt_message['type']] == 'hub_alerts':
				# Ignore "status OK" messages
				if bt_message['status'] == True:
					BTLegoMario.dp(msg_prefix+"ALERT! "+bt_message['alert_type_str']+" - "+bt_message['operation_str'])
					self.message_queue.put(('error','message',bt_message['alert_type_str']+" - "+bt_message['operation_str']))

			elif BTLego.message_type_str[bt_message['type']] == 'hub_actions':
				self.decode_hub_action(bt_message)

			elif BTLego.message_type_str[bt_message['type']] == 'port_mode_info':
				# Debug stuff for the ports and modes, similar to list command on BuildHAT
				BTLegoMario.dp(msg_prefix+bt_message['readable'],3)

			else:
				# debug for messages we've never seen before
				BTLegoMario.dp(msg_prefix+"-?- "+bt_message['readable'],1)

		BTLegoMario.dp("Draining for: "+bt_message['readable'],3)
		await self.drain_messages()

	# ---- Make data useful ----

	def decode_pants_data(self, data):
		if len(data) == 1:
			BTLegoMario.dp(self.which_player+" put on "+BTLegoMario.mario_pants_to_string(data[0])+" pants",2)
			if data[0] in self.pants_codes:
				self.message_queue.put(('pants','pants',data[0]))
			else:
				BTLegoMario.dp(self.which_player+" put on unknown pants code "+str(hex(data[0])))
		else:
			BTLegoMario.dp(self.which_player+" UNKNOWN PANTS DATA, WEIRD LENGTH OF "+len(data)+":"+" ".join(hex(n) for n in data))

	# RGB Mode 0
	def decode_scanner_data(self, data):
		if len(data) != 4:
			BTLegoMario.dp(self.which_player+" UNKNOWN SCANNER DATA, WEIRD LENGTH OF "+len(data)+":"+" ".join(hex(n) for n in data))
			return

		scantype = None
		if data[2] == 0xff and data[3] == 0xff:
			scantype = 'barcode'
		if data[0] == 0xff and data[1] == 0xff:
			if scantype == 'barcode':
				scantype = 'nothing'
			else:
				scantype = 'color'

		if not scantype:
			BTLegoMario.dp(self.which_player+" UNKNOWN SCANNER DATA:"+" ".join(hex(n) for n in data))
			return

		if scantype == 'barcode':
			barcode_int = BTLegoMario.mario_bytes_to_int(data[0:2])
			# Max 16-bit signed int, Github Issue #4
			if barcode_int != 32767:
				# Happens when Black is used as a color
				code_info = BTLegoMario.get_code_info(barcode_int)
				BTLegoMario.dp(self.which_player+" scanned "+code_info['label']+" (" + code_info['barcode']+ " "+str(barcode_int)+")",2)
				self.message_queue.put(('scanner','code',(code_info['barcode'], barcode_int)))
			else:
				self.message_queue.put(('error','message','Scanned malformed code'))
		elif scantype == 'color':
			color = BTLegoMario.mario_bytes_to_solid_color(data[2:4])
			BTLegoMario.dp(self.which_player+" scanned color "+color,2)
			self.message_queue.put(('scanner','color',color))
		else:
			#scantype == 'nothing':
			BTLegoMario.dp(self.which_player+" scanned nothing",2)

	# IMU Mode 0,1
	def decode_accel_data(self, data):
		# The "default" value is around 32, which seems like g at 32 ft/s^2
		# But when you flip a sensor 180, it's -15
		# "Waggle" is probably detected by rapid accelerometer events that don't meaningfully change the values

		# RAW: Mode 0
		if len(data) == 3:
			# Put mario on his right side and he will register ~32
			lr_accel = int(data[0])
			if lr_accel > 127:
				lr_accel = -(127-(lr_accel>>1))

			# Stand mario up to register ~32
			ud_accel = int(data[1])
			if ud_accel > 127:
				ud_accel = -(127-(ud_accel>>1))

			# Put mario on his back and he will register ~32
			fb_accel = int(data[2])
			if fb_accel > 127:
				fb_accel = -(127-(fb_accel>>1))

			BTLegoMario.dp(self.which_player+" accel down "+str(ud_accel)+" accel right "+str(lr_accel)+" accel backwards "+str(fb_accel),2)

		# GEST: Mode 1
		# 0x8 0x0 0x45 0x0 [ 0x0 0x80 0x0 0x80 ]
		elif len(data) == 4:

			little_32b_int = int.from_bytes(data, byteorder="little", signed=False)
			if not little_32b_int == 0x0:
				#print("full: "+'{:032b}'.format(little_32b_int))

				first_16b_int = int.from_bytes(data[:2], byteorder="little", signed=False)
				last_16b_int = int.from_bytes(data[2:], byteorder="little", signed=False)
				if (first_16b_int != last_16b_int):
					print("split ints: "+'{:016b}'.format(first_16b_int)+'_'+'{:016b}'.format(last_16b_int))
				else:
					# https://github.com/djipko/legomario.py/blob/master/legomario.py
					# https://github.com/benthomasson/legomario/commit/16670878fb0be28481733fefee7754adc8820e1a

					detect_bit = True
					#print("matched ints: "+'{:016b}'.format(first_16b_int))

					# Walk						0000 0000_0x00000x
					# Odd that I've never seen 0x1 or 0x40 by themselves
					# djipko claims 0x1 is bump
					# Just walk the player side to side on a surface
					# Can also generate by wobbling a rail car front to back within it's limits
					PLAYER_WALK					= 0x40 + 0x1

					# Seen live after a slam 	0000 0000_000000x0
					PLAYER_DUNNO_2				= 0x2

					# Seen live	after jump		0000 0000_00000100
					# benthomasson (fly) if paired with direction change 0x1000
					PLAYER_DUNNO_4				= 0x4

					# Flip						0000 0000_0000x000	benthomasson (hardshake)
					# Do a flip on peach's swing (BRYVG) and it will make a magic sound
					# and emit this gesture.  Doesn't seem to matter which direction (front or back)
					# Sideways does not work
					PLAYER_FLIP					= 0x8

					# Shake						0000 0000_00010000	djipko (shake), benthomasson (flip) (if split and lower are 0x0?)
					# benthomasson has "flip" as 0x100000 in a 32-bit int, which is 0x10 if the high bits are actually a 16-bit int
					#	This showed up on peach as a matched set of 0x10
					# Use the peach swing quickly
					# Enough of these make the player "dizzy"
					PLAYER_SHAKE				= 0x10

					# Tornado spin				0000 0000_00100000	benthomasson (spin)
					# Hold the player upright in your hand, put your elbow on a table as a pivot,
					# then move the player around in a circle (~4in diameter)
					# Usually also makes them dizzy
					# Doesn't seem to work inverted (holding the player above the table with your elbow in the air)
					# Not sure how this would be generated in a set
					PLAYER_TORNADO				= 0x20

					# 0x40? Never seen

					# 0x80? Never seen

					# Turn (clockwise)			0000 000x_00000000	djipko (turning)
					PLAYER_CLOCKWISE			= 0x100

					# Move quickly				0000 00x0_00000000	djipko (fastmove)
					# Peach swing when done moderately quickly
					# Emitted constantly on the Piranha Plant Power Slide (GRPLB)
					# Triggers for "ouch" on this code seem to be anything that is not PLAYER_JUMP or PLAYER_WALK
					PLAYER_MOVING				= 0x200

					# Disturbed					0000 0x00_00000000	djipko (translation)
					PLAYER_DISTURBED			= 0x400

					# Crash	(violent stop)		0000 x000_00000000	djipko (high fall crash)
					# Side to side shaking on a rail generates this
					PLAYER_CRASH				= 0x800

					# Sudden stop				000x 0000_00000000	djipko (direction change)
					# Easy to replicate on Piranha Plant Power Slide (GRPLB)
					# Ride Peach's swing sideways to constantly generate, so detection seems directionally biased
					# Moving up and down quickly generates it a lot
					PLAYER_SUDDEN_STOP			= 0x1000

					# Inverse turn				00x0 000x_00000000	djipko (reverse)
					PLAYER_INVERT_TURN			= 0x2000 # + 0x100 Mask to check only if turn inverts

					# Flying roll				0x00 0000_00000000	benthomasson (roll)
					# Player needs to be horizontal like they're flying and then quickly rolled
					PLAYER_ROLL					= 0x4000

					# Jump						x000 0000_00000000	djipko (jump)
					PLAYER_JUMP					= 0x8000

					# "Throw" or "tip" is MOVE then JUMP?  Mario's internal code for dealing with
					# throwing turnips or eating cake and fruit seems to not reliably match
					# the bluetooth data, which isn't a new phenomenon...

					# Sometimes mario can return a bunch of nonsense at the same time like, clockwise jump direction change
					# This elif ladder obviously only dones one of them at a time
					# Debating how to message that

					if bool (first_16b_int & PLAYER_CLOCKWISE ):
						if bool (first_16b_int & PLAYER_INVERT_TURN ):
							self.message_queue.put(('gesture','turn','counterclockwise'))
							pass
						else:
							self.message_queue.put(('gesture','turn','clockwise'))
							pass

					elif bool (first_16b_int & PLAYER_DISTURBED ):
						self.message_queue.put(('gesture','disturbed',None))
						pass

					elif bool (first_16b_int & PLAYER_MOVING ):
						self.message_queue.put(('gesture','moving',None))
						pass

					elif bool (first_16b_int & PLAYER_JUMP ):
						self.message_queue.put(('gesture','jump',None))
						pass

					elif bool (first_16b_int & PLAYER_WALK ):
						self.message_queue.put(('gesture','walk',None))
						pass

					elif bool (first_16b_int & PLAYER_SHAKE ):
						self.message_queue.put(('gesture','shake',None))
						pass

					elif bool (first_16b_int & PLAYER_FLIP ):
						self.message_queue.put(('gesture','flip',None))
						pass

					elif bool (first_16b_int & PLAYER_SUDDEN_STOP ):
						self.message_queue.put(('gesture','stop',None))
						pass

					elif bool (first_16b_int & PLAYER_CRASH ):
						self.message_queue.put(('gesture','crash',None))
						pass

					elif bool (first_16b_int & PLAYER_TORNADO ):
						self.message_queue.put(('gesture','tornado',None))
						pass

					elif bool (first_16b_int & PLAYER_ROLL ):
						self.message_queue.put(('gesture','roll',None))
						pass

					elif bool (first_16b_int & PLAYER_DUNNO_4 ):
						print("BIT: dunno4?")
						pass

					elif bool (first_16b_int & PLAYER_DUNNO_2 ):
						print("BIT: dunno2?")
						pass

					elif bool (first_16b_int & (0x1 | 0x40 | 0x80) ):
						print("WHAT DID YOU DO?!  matched ints: "+'{:08b}'.format(data[1])+'_'+'{:08b}'.format(data[0]))

					else:
						detect_bit = False
						print("matched ints: "+'{:08b}'.format(data[1])+'_'+'{:08b}'.format(data[0]))

			else:
				# Maybe this is "done?", as sometimes you'll see a bunch of gestures and then this
				#print("ignoring empty gesture")
				return

			notes= ""
			if data[0] != data[2]:
				notes += "NOTE:odd mismatch:"
			if data[1] != data[3]:
				notes += "NOTE:even mismatch:"
			if (data[0] and data[1]) or (data[2] and data[3]) or (data[0] and data[3]) or (data[1] and data[2]):
				# "matched ints"
				#notes += "NOTE:dual paring:"
				pass

			if notes:
				BTLegoMario.dp(self.which_player+" gesture data:"+notes+" ".join(hex(n) for n in data),2)

	def decode_event_data(self, data):

		# Mode 2
		if len(data) == 4:
			#													TYP		KEY		VAL (uint16)
			#luigi Data on Mario Events port:0x8 0x0 0x45 0x3	0x9 	0x20	0x1 0x0

			event_type = data[0]
			event_key = data[1]
			value = BTLegoMario.mario_bytes_to_int(data[2:])

			# 0x0 0x0 0x0 0x0	when powered on or when subscribed?  FIXME: after callbacks get set, check which one

			decoded_something = False
			if event_type == 0x2:
				if event_key == 0x18:
					#0x2 0x18 0x2 0x0
					#0x2 0x18 0x1 0x0
					if value == 2:
						BTLegoMario.dp(self.which_player+" fell asleep",2)
						self.message_queue.put(('event','consciousness','asleep'))
						decoded_something = True
					elif value == 1:
						BTLegoMario.dp(self.which_player+" woke up",2)
						self.message_queue.put(('event','consciousness','awake'))
						decoded_something = True
			elif event_type == 0x1:
				if event_key == 0x18:
					if value == 0:
						# 0x1 0x18 0x0 0x0
						# Happens a little while after the flag, sometimes on bootup too
						BTLegoMario.dp(self.which_player+" course status has been reset",2)
						decoded_something = True

			if event_key == 0x20:
				# hat tip to https://github.com/bhawkes/lego-mario-web-bluetooth/blob/master/pages/index.vue
				BTLegoMario.dp(self.which_player+" now has "+str(value)+" coins (obtained via "+str(hex(event_type))+")",2)
				self.message_queue.put(('event','coincount',(value, event_type)))
					# via:
					# 0x9:	Bouncing around randomly
					# 0x42:	Goomba
					# 0x44:	Whatever complexity stomping a Spiny is
					# 0xb0: Fireball blip nothing
				decoded_something = True

			# Start a course
			# 0x72 0x38 0x2 0x0	First this
			# 0x1 0x18 0x1 0x0	Then this

			# Last message before powered off via button
			# 0x73 0x38 0x0 0x0

			# Unidentified "Idle" or jumping around chatter
			# 0x0 0x0 0x0 0x0		Probably init response when subscribed to port
			# 0x62 0x38 0x0 0x0
			# 0x57 0x38 0x0 0x0
			# 0x57 0x38 0x1 0x0		# SOMETIMES a wild 0x1 appears!

			# maybe related to low battery flashing
			# 0x61 0x38 0x8 0x0
			# 0x61 0x38 0x3 0x0
			# 0x61 0x38 0x8 0x0

			# Hanging out and doing nothing with fire pants on
			# 0x62 0x38 0x0 0x0
			# 0x61 0x38 0x5 0x0
			# 0x5e 0x38 0x0 0x0
			# 0x61 0x38 0x8 0x0
			# 0x61 0x38 0x3 0x0
			# 0x61 0x38 0x8 0x0
			# 0x61 0x38 0x3 0x0
			# 0x66 0x38 0x0 0x0

			# 0x5e 0x38 0x0 0x0		a little while after first powered on

			# Dumped on app connect
			# 0x1 0x19 0x3 0x0
			# 0x2 0x19 0x8 0x0
			# 0x10 0x19 0x1 0x0
			# 0x11 0x19 0x7 0x0
			# 0x80 0x1 0x0 0x0
			# 0x15 0x1 0x8 0x0		Pants related (power up/down?)
			# 0x1 0x18 0x0 0x0		DONE: Course status reset
			# 0x1 0x40 0x1 0x0
			# 0x2 0x40 0x1 0x0
			# 0x1 0x30 0x0 0x0

			# Abrupt jump
			#peach event data:0x57 0x38 0x0 0x0
			#peach event data:0x62 0x38 0x0 0x0


			if not decoded_something:
				BTLegoMario.dp(self.which_player+" event data:"+" ".join(hex(n) for n in data),2)
		else:
			BTLegoMario.dp(self.which_player+" non-mode-2-style event data:"+" ".join(hex(n) for n in data),2)

		pass

	def decode_advertising_name(self, name):
		#LEGO Mario_j_r

		if name.startswith("LEGO Mario_") == False or len(name) != 14:
			# print(name.encode("utf-8").hex())
			if name == "LEGO Peach    ":
				# Four spaces after the name
				BTLegoMario.dp("Peach has no icon or color set")
			else:
				BTLegoMario.dp("Unusual advertising name set:"+name)
			return

		icon = ord(name[11])
		color = ord(name[13])

		if not icon in BTLegoMario.app_icon_names:
			BTLegoMario.dp("Unknown icon:"+str(hex(icon)))
			return

		if not color in BTLegoMario.app_icon_color_names:
			BTLegoMario.dp("Unknown icon color:"+str(hex(color)))
			return

		if BTLegoMario.DEBUG >= 2:
			color_str =  BTLegoMario.app_icon_color_names[color]
			icon_str =  BTLegoMario.app_icon_names[icon]
			BTLegoMario.dp(self.which_player+" icon is set to "+color_str+" "+icon_str,2)

		self.message_queue.put(('info','icon',(icon,color)))

	def decode_hub_action(self, bt_message):
		BTLegoMario.dp(self.which_player+" "+bt_message['action_str'],2)
		# BTLego.hub_action_type
		if bt_message['action'] == 0x30:
			self.message_queue.put(('event','power','turned_off'))
		if bt_message['action'] == 0x31:
			self.message_queue.put(('event','bt','disconnected'))

	# ---- Scanner code utilities ----

	def get_code_info(barcode_int):
		info = {
			'id':barcode_int,
			'barcode':BTLegoMario.int_to_scanner_code(barcode_int)
		}
		if BTLegoMario.code_data:
			BTLegoMario.dp("Scanning database for code "+str(barcode_int)+"...",3)
			if BTLegoMario.code_data['version'] == 7:
				info = BTLegoMario.populate_code_info_version_7(info)

		if not 'label' in info:
			info['label'] = 'x_'+info['barcode']+"_"
		elif not info['label']:
			info['label'] = 'x_'+info['barcode']+"_"
		return info

	def get_label_for_scanner_code_info(barcode_str):
		if BTLegoMario.code_data:
			BTLegoMario.dp("Scanning database for code "+barcode_str+"..",3)
			if BTLegoMario.code_data['version'] == 7:
				for code in BTLegoMario.code_data['codes']:
					if code['code'] == barcode_str:
						return code['label']
		return ""

	def populate_code_info_version_7(info):
		# FIXME: Kind of a junky way to search them...
		for code in BTLegoMario.code_data['codes']:
			if code['code'] == info['barcode']:
				info['label'] = code['label']
				if 'note' in code:
					info['note'] = code['note']
				if 'use' in code:
					info['use'] = code['use']
				if 'blpns' in code:
					info['blpns'] = code['blpns']
		if not 'label' in info:
			for code in BTLegoMario.code_data['unidentified']:
				if code['code'] == info['barcode']:
					if 'label' in code:
						info['label'] = code['label']
					else:
						info['label'] = None
					if 'note' in code:
						info['note'] = code['note']
		return info

	def generate_gr_codespace():
		prefix = "GR"
		# Lowest value to highest value
		mario_numbers = ['B','P','?','Y','V','T','L']
		potential_position_1 = mario_numbers[:]
		count = 1
		for p1 in potential_position_1:
			potential_position_2 = mario_numbers[:]
			potential_position_2.remove(p1)
			for p2 in potential_position_2:
				potential_position_3 = potential_position_2[:]
				potential_position_3.remove(p2)
				for p3 in potential_position_3:
					code = None
					mirrorcode = ""
					if p1 != '?' and p2 != '?' and p3 != '?':
						code = prefix+p1+p2+p3
						mirrorcode = BTLegoMario.does_code_have_mirror(code)
						if mirrorcode:
							# When scanned backwards, this code will read as the BR code in mirrorcode
							# But the number returned is associated with the GR codespace
							code = code+"\t"+mirrorcode
						else:
							code = code+"\t"
					else:
						# Contains forbidden "color"
						# Theorized to be black through experimentation, by @tomalphin on github, coincidentally(?) colored as black by @bricklife
						# https://github.com/mutesplash/legomario/issues/4#issuecomment-1368106277
						# Other colors don't even generate bluetooth responses?
						code = "-----\t"
					mario_hex = BTLegoMario.int_to_mario_bytes(count)
					BTLegoMario.dp(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex),4)
					BTLegoMario.gr_codespace[count] = code
					count += 1

	def generate_br_codespace():
		prefix = "BR"
		mario_numbers = ['G','P','?','Y','V','T','L']
		potential_position_1 = mario_numbers[:]
		# resume from the end of the GR space
		count = 211
		for p1 in potential_position_1:
			potential_position_2 = mario_numbers[:]
			potential_position_2.remove(p1)
			for p2 in potential_position_2:
				potential_position_3 = potential_position_2[:]
				potential_position_3.remove(p2)
				for p3 in potential_position_3:
					code = None
					mirrorcode = ""
					if p1 != '?' and p2 != '?' and p3 != '?':
						# Note order compared to GR.  I don't quite understand why
						code = prefix+p1+p3+p2
						mirrorcode = BTLegoMario.does_code_have_mirror(code)
						if mirrorcode:
							# When scanned "backwards" this code is equivalent to a GR code in mirrorcode
							# Ignore it because the GR code's number is the one that is returned
							code = "--M--\t"+mirrorcode
						else:
							code = code+"\t"
					else:
						code = "-----\t"
					mario_hex = BTLegoMario.int_to_mario_bytes(count)
					BTLegoMario.dp(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex),4)
					BTLegoMario.br_codespace[count] = code
					count += 1

	def print_codespace():
		# i\tcode\tmirror\tlabel\tscanner hex\tbinary
		BTLegoMario.generate_codespace()
		BTLegoMario.print_gr_codespace()
		BTLegoMario.print_br_codespace()

	def generate_codespace():
		if not BTLegoMario.gr_codespace:
			BTLegoMario.generate_gr_codespace()
		if not BTLegoMario.br_codespace:
			BTLegoMario.generate_br_codespace()

	def print_gr_codespace():
		if not BTLegoMario.gr_codespace:
			BTLegoMario.generate_gr_codespace()
		BTLegoMario.print_cached_codespace(BTLegoMario.gr_codespace)

	def print_br_codespace():
		if not BTLegoMario.br_codespace:
			BTLegoMario.generate_br_codespace()
		BTLegoMario.print_cached_codespace(BTLegoMario.br_codespace)

	def print_cached_codespace(codespace_cache):
		for i,c in codespace_cache.items():
			mirrorcode = ""
			splitcode = c.split('\t')
			if isinstance(splitcode, list):
				c = splitcode[0]
				if splitcode[1]:
					mirrorcode = splitcode[1]
			mario_hex = BTLegoMario.int_to_mario_bytes(i)

			c_info = BTLegoMario.get_code_info(i)
			if c == "-----":
				c_info['label'] = ""
			elif c == "--M--":
				c_info['label'] = BTLegoMario.get_label_for_scanner_code_info(mirrorcode)

			# Pad these out
			c_info['label'] = "{:<8}".format(c_info['label'])
			if not mirrorcode:
				mirrorcode = "{:<5}".format(mirrorcode)

			print(str(i)+"\t"+c+"\t"+mirrorcode+"\t"+c_info['label']+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex)+"\t"+'{:09b}'.format(i))

	def does_code_have_mirror(mariocode):
		if mariocode.startswith('-'):
			return None
		if mariocode.startswith('BR'):
			if mariocode[2] == 'G':
				return 'GRB'+mariocode[4]+mariocode[3]
			return None
		elif mariocode.startswith('GR'):
			if mariocode[2] == 'B':
				return 'BRG'+mariocode[4]+mariocode[3]
			return None
		else:
			return "INVAL"

	def int_to_scanner_code(mario_int):
		BTLegoMario.generate_codespace()
		code = None
		if mario_int in BTLegoMario.br_codespace:
			code = BTLegoMario.br_codespace[mario_int]
		elif mario_int in BTLegoMario.gr_codespace:
			code = BTLegoMario.gr_codespace[mario_int]
		else:
			return "--U--"
		splitcode = code.split('\t')
		if isinstance(splitcode, list):
			return splitcode[0]
		else:
			return code

	# ---- Random stuff ----

	# Probably useful instead of having to remember to do this when working with bluetooth
	def mario_bytes_to_int(mario_byte_array):
		return int.from_bytes(mario_byte_array, byteorder="little")

	# Not useful anywhere but here, IMO
	# what is this, uint16?  put this in the base
	def int_to_mario_bytes(mario_int):
		return mario_int.to_bytes(2, byteorder="little")

	def mario_bytes_to_solid_color(mariobytes):
		color = BTLegoMario.mario_bytes_to_int(mariobytes)
		if color in BTLegoMario.solid_colors:
			return BTLegoMario.solid_colors[color]
		else:
			return 'unknown('+str(color)+')'

	def mario_pants_to_string(mariobyte):
		if mariobyte in BTLegoMario.pants_codes:
			return BTLegoMario.pants_codes[mariobyte]
		else:
			return 'unknown('+str(hex(mariobyte))+')'

	def dp(pstr, level=1):
		if BTLegoMario.DEBUG:
			if BTLegoMario.DEBUG >= level:
				print(pstr)

	# ---- Bluetooth port writes ----

	async def set_port_subscriptions(self, portlist):
		# array of 3-item arrays [port, mode, subscribe on/off]
		if isinstance(portlist, Iterable):
			for port_settings in portlist:
				if isinstance(port_settings, Iterable) and len(port_settings) == 3:
					await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, BTLegoMario.port_inport_format_setup_bytes(port_settings[0],port_settings[1],port_settings[2]))
					await asyncio.sleep(0.1)

	async def set_icon(self, icon, color):
		if icon not in BTLegoMario.app_icon_ints:
			BTLegoMario.dp("ERROR: Attempted to set invalid icon:"+icon)
			return
		if color not in BTLegoMario.app_icon_color_ints:
			BTLegoMario.dp("ERROR: Attempted to set invalid color for icon:"+color)

		set_name_bytes = bytearray([
			0x00,	# len placeholder
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x1,	# 'Advertising Name'
			0x1		# 'Set'
		])

		set_name_bytes = set_name_bytes + "LEGO Mario_I_C".encode()

		set_name_bytes[0] = len(set_name_bytes)
		set_name_bytes[16] = BTLegoMario.app_icon_ints[icon]
		set_name_bytes[18] = BTLegoMario.app_icon_color_ints[color]

		await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, set_name_bytes)
		await asyncio.sleep(0.1)

	async def erase_icon(self):
		if self.which_player != 'peach':
			BTLegoMario.dp("ERROR: Don't know how to erase any player except peach")
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

		await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, set_name_bytes)
		await asyncio.sleep(0.1)

	async def set_volume(self, volume):
		if volume > 100 or volume < 0:
			return
		# The levels in the app are 100, 90, 75, 50, 0
		# Which is weird, but whatever
		set_volume_bytes = bytearray([
			0x06,	# len placeholder
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x12,	# 'Mario Volume'
			0x1,	# 'Set'
			volume
		])

		await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, set_volume_bytes)
		await asyncio.sleep(0.1)

	async def set_updates_for_hub_properties(self, hub_properties):
		# array of [str(hub_property_str),bool] arrays
		if isinstance(hub_properties, Iterable):
			for hub_property_settings in hub_properties:
				if isinstance(hub_property_settings, Iterable) and len(hub_property_settings) == 2:
					hub_property = str(hub_property_settings[0])
					hub_property_set_updates = bool(hub_property_settings[1])
					if hub_property in self.hub_property_ints:
						hub_property_int = self.hub_property_ints[hub_property]
						if hub_property_int in self.subscribable_hub_properties:
							hub_property_operation = 0x3
							if hub_property_set_updates:
								BTLegoMario.dp("Requesting updates for hub property: "+hub_property,2)
								hub_property_operation = 0x2
							else:
								BTLegoMario.dp("Disabling updates for hub property: "+hub_property,2)
								pass
							hub_property_update_subscription_bytes = bytearray([
								0x05,	# len
								0x00,	# padding but maybe stuff in the future (:
								0x1,	# 'hub_properties'
								hub_property_int,
								hub_property_operation
							])
							await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, hub_property_update_subscription_bytes)
							await asyncio.sleep(0.1)

	async def turn_off(self):
		name_update_bytes = bytearray([
			0x04,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x2,	# 'hub_actions'
			0x1		# BTLego.hub_action_type: 'Switch Off Hub'  (Don't use 0x2f, powers down as if you yanked the battery)
		])
		await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)

	async def request_name_update(self):
		# Triggers hub_properties message
		name_update_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x1,	# 'Advertising Name'
			0x5		# 'Request Update'
		])
		await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)

	async def request_volume_update(self):
		# Triggers hub_properties message
		name_update_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x12,	# 'Mario Volume'
			0x5		# 'Request Update'
		])
		await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)

	async def request_version_update(self):
		# Triggers hub_properties message
		name_update_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x3,	# 'Firmware version'
			0x5		# 'Request Update'
		])
		await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)

		name_update_bytes = bytearray([
			0x05,	# len
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x4,	# 'Hardware version'
			0x5		# 'Request Update'
		])
		await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)


	def port_inport_format_setup_bytes(port, mode, enable):
		# original hint from https://github.com/salendron/pyLegoMario
		# Port Input Format Setup (Single) message

		# Sending this results in port_input_format_single response
		ebyte = 0
		if enable:
			ebyte = 1
		# Len, 0x0, Port input format (single), port, mode, delta interval of 5 (uint32), notification enable/disable
		return bytearray([0x0A, 0x00, 0x41, port, mode, 0x05, 0x00, 0x00, 0x00, ebyte])


