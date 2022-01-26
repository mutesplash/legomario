import asyncio
from bleak import BleakClient
from collections.abc import Iterable
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
	which_brother = None
	address = None
	lock = None
	client = None
	connected = False

	# keep around for whatever
	device = None
	advertisement = None

	characteristic_uuid = '00001624-1212-efde-1623-785feabcd123'
	hub_service_uuid = '00001623-1212-efde-1623-785feabcd123'

	# https://github.com/bricklife/LEGO-Mario-Reveng
	IMU_PORT = 0		# Inertial Monitoring Unit?
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
	solid_colors = {
		19:'white',
		21:'red',
		23:'blue',		# For some reason, this doesn't return even if mario puts himself in water on the screen
		24:'yellow',
		26:'black',
		37:'green',
		106:'orange',	# listed as brown elsewhere, but the NES code "knows" orange and orange scans as this
		268:'purple',
		312:'nougat',
		322:'cyan'
	}

	pants_codes = {
		0x0:'no',		# Sometimes mario registers 0x2 as no pants, might be a pin problem?
		0x3:'bee',		# Acts strange and won't send messages when these pants are on.  Needs more testing
		0x5:'luigi',
		0x6:'frog',
		0xa:'tanooki',
		0xc:'propeller',
		0x11:'cat',
		0x12:'fire',
		0x14:'penguin',
		0x21:'mario',	# Sometimes mario registers 0x20 as mario pants, might be a pin problem?
		0x22:'builder'
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

		BTLegoMario.code_data = json_code_dict
		self.__init_port_data(0,0x47)
		self.__init_port_data(1,0x49)
		self.__init_port_data(2,0x4A)
		self.__init_port_data(3,0x46)
		self.__init_port_data(4,0x55)
		self.__init_port_data(6,0x14)

		# reverse map some dicts so you can index them either way
		self.app_icon_ints = dict(map(reversed, self.app_icon_names.items()))
		self.app_icon_color_ints = dict(map(reversed, self.app_icon_color_names.items()))

		self.lock = asyncio.Lock()

	def __init_port_data(self, port, port_id):
		self.port_data[port] = {
			'io_type_id':port_id,
			'name':BTLego.io_type_id_str[port_id],
			'single_input': False
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
			if advertisement_data.manufacturer_data[919][1] == 0x44:
				return 'luigi'
			elif advertisement_data.manufacturer_data[919][1] == 0x43:
				return 'mario'
			else:
				return 'UNKNOWN_MARIO'
		return None

	async def connect(self, device, advertisement_data):
		async with self.lock:
			self.which_brother = BTLegoMario.which_device(advertisement_data)
			print("Connecting to "+str(self.which_brother)+"...")
			self.device = device
			self.advertisement = advertisement_data
			try:
				async with BleakClient(device.address) as self.client:
					if not self.client.is_connected:
						print("Failed to connect after client creation")
						return
					print("Connected to "+self.which_brother+"! ("+str(device.name)+")")
					self.connected = True
					await self.client.start_notify(BTLegoMario.characteristic_uuid, self.mario_events)
					await asyncio.sleep(0.1)

					await self.request_name_update()
					await self.set_updates_for_hub_properties([
						#['Advertising Name',True],	# I guess this works different than requesting the update because something else could change it, but then THAT would cause an update message
						#['RSSI',True],				# Doesn't really update for whatever reason
						#['Battery Voltage',True],	# Transmits updates pretty frequently
						['Button',True]				# Works as advertised (the "button" is the bluetooth button)
					])

					await self.set_port_subscriptions([
						[self.RGB_PORT,0,True],
						[self.EVENTS_PORT,2,True],
						# [self.IMU_PORT,1,True],
						[self.PANTS_PORT,0,True]
					])

					#await self.set_icon('star', 'green')

					while self.client.is_connected:
						await asyncio.sleep(0.05)
					self.connected = False
					print(self.which_brother+" has disconnected.")

			except Exception as e:
				print("Unable to connect to "+str(device.address) + ": "+str(e))

	async def mario_events(self, sender, data):

		bt_message = BTLego.decode_payload(data)
		msg_prefix = self.which_brother+" "

		if bt_message['error']:
			print(msg_prefix+"ERR:"+bt_message['readable'])
		else:
			if BTLego.message_type_str[bt_message['type']] == 'port_input_format_single':
				msg = "Disabled notifications on "
				if bt_message['notifications']:
					# Returned typically after gatt write
					msg = "Enabled notifications on "

				port_text = "port "+str(bt_message['port'])
				if bt_message['port'] in BTLegoMario.port_data:
					# Sometimes the hub_attached_io messages don't come in before the port subscriptions do
					port_text = BTLegoMario.port_data[bt_message['port']]['name']+" port"

				print(msg_prefix+msg+port_text+", mode "+str(bt_message['mode']))

			elif BTLego.message_type_str[bt_message['type']] == 'hub_attached_io':
				if BTLego.io_event_type_str[bt_message['event']] == 'attached':
					dev = "UNKNOWN DEVICE"
					if bt_message['io_type_id'] in BTLego.io_type_id_str:
						dev = BTLego.io_type_id_str[bt_message['io_type_id']]
					if bt_message['port'] in self.port_data:
						print(msg_prefix+"Re-attached "+dev+" on port "+str(bt_message['port']))
					else:
						print(msg_prefix+"Attached "+dev+" on port "+str(bt_message['port']))

					self.port_data[bt_message['port']] = {
						'io_type_id':bt_message['io_type_id'],
						'name':dev,
						'status':bt_message['event']
					}
				elif BTLego.io_event_type_str[bt_message['event']] == 'detached':
					self.port_data.pop(bt_message['port'],None)
					print(msg_prefix+"Detached "+dev+" on port "+str(bt_message['port']))
				else:
					# debug this weird thing
					print(msg_prefix+"-X- "+bt_message['readable'])

			elif BTLego.message_type_str[bt_message['type']] == 'port_value_single':
				if not bt_message['port'] in self.port_data:
					print(msg_prefix+"ERR: Attempted to send data to unconfigured port "+str(bt_message['port']))
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
						port_text = self.port_data[bt_message['port']]['name']+" port"
						print(msg_prefix+"Data on "+port_text+":"+" ".join(hex(n) for n in data))

			elif BTLego.message_type_str[bt_message['type']] == 'hub_properties':
				# The app seems to be able to subscribe to Battery Voltage and get it sent constantly

				if not BTLego.hub_property_op_str[bt_message['operation']] == 'Update':
					# everything else is a write, so you shouldn't be getting these messages!
					print(msg_prefix+"ERR NOT UPDATE: "+bt_message['readable'])

				else:
					if not bt_message['property'] in BTLego.hub_property_str:
						print(msg_prefix+"Unknown property "+bt_message['readable'])
					else:
						if BTLego.hub_property_str[bt_message['property']] == 'Button':
							if bt_message['value']:
								print(msg_prefix+"Bluetooth button pressed!")
							else:
								# Well, nobody cares if it WASN'T pressed...
								pass

						elif BTLego.hub_property_str[bt_message['property']] == 'Battery Voltage':
							print(msg_prefix+"Battery is at "+str(bt_message['value'])+"%")

						elif BTLego.hub_property_str[bt_message['property']] == 'Advertising Name':
							self.decode_advertising_name(bt_message['value'])

						else:
							print(msg_prefix+bt_message['readable'])

			elif BTLego.message_type_str[bt_message['type']] == 'port_output_command_feedback':
				# Don't really care about these messages?
				#print(msg_prefix+" "+bt_message['readable'])
				pass

			elif BTLego.message_type_str[bt_message['type']] == 'hub_alerts':

				# Ignore "status OK" messages
				if bt_message['status'] == True:
					print(msg_prefix+"ALERT! "+bt_message['alert_type_str']+" - "+bt_message['operation_str'])

			elif BTLego.message_type_str[bt_message['type']] == 'hub_actions':
				# Usually a "will" message...
				print(msg_prefix+bt_message['action_str'])

			elif BTLego.message_type_str[bt_message['type']] == 'port_mode_info':
				# Debug stuff for the ports and modes, similar to list command on BuildHAT
				print(msg_prefix+bt_message['readable'])

			else:
				# debug for messages we've never seen before
				print(msg_prefix+"-?- "+bt_message['readable'])

	# ---- Make data useful ----

	def decode_pants_data(self, data):
		if len(data) == 1:
			print(self.which_brother+" put on "+BTLegoMario.mario_pants_to_string(data[0])+" pants")
		else:
			print(self.which_brother+" UNKNOWN PANTS DATA, WEIRD LENGTH OF "+len(data)+":"+" ".join(hex(n) for n in data))

	# RGB Mode 0
	def decode_scanner_data(self, data):
		if len(data) != 4:
			print(self.which_brother+" UNKNOWN SCANNER DATA, WEIRD LENGTH OF "+len(data)+":"+" ".join(hex(n) for n in data))
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
			print(self.which_brother+" UNKNOWN SCANNER DATA:"+" ".join(hex(n) for n in data))
			return

		if scantype == 'barcode':
			barcode_int = BTLegoMario.mario_bytes_to_int(data[0:2])
			code_info = BTLegoMario.get_code_info(barcode_int)
			print(self.which_brother+" scanned "+code_info['label']+" (" + code_info['barcode']+ " "+str(barcode_int)+")")
		elif scantype == 'color':
			color = BTLegoMario.mario_bytes_to_solid_color(data[2:4])
			print (self.which_brother+" scanned color "+color)
		else:
			#scantype == 'nothing':
			print(self.which_brother+" scanned nothing")

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

			print(self.which_brother+" accel down "+str(ud_accel)+" accel right "+str(lr_accel)+" accel backwards "+str(fb_accel))

		# GEST: Mode 1
		# 0x8 0x0 0x45 0x0 0x0 0x80 0x0 0x80
		elif len(data) == 4:
			notes= ""
			if data[0] != data[2]:
				notes += "NOTE:odd mismatch:"
			if data[1] != data[3]:
				notes += "NOTE:even mismatch:"
			if (data[0] and data[1]) or (data[2] and data[3]) or (data[0] and data[3]) or (data[1] and data[2]):
				notes += "NOTE:dual paring:"

			# Ignore "no gesture"
			if not int.from_bytes(data, byteorder="little", signed=False) == 0x0:
				# FIXME: match up some patterns to real life
				if notes:
					print(self.which_brother+" gesture data:"+notes+" ".join(hex(n) for n in data))
				else:
					if data[0]:
						print(self.which_brother+" gesture data ODD:"+str(data[0])+" ("+str(hex(data[0]))+")")
					elif data[1]:
						print(self.which_brother+" gesture data EVEN:"+str(data[1])+" ("+str(hex(data[1]))+")")
					else:
						print(self.which_brother+" gesture data logic failure:"+" ".join(hex(n) for n in data))

	def decode_event_data(self, data):

		# Mode 2
		if len(data) == 4:
			# hat tip to hints from https://github.com/bhawkes/lego-mario-web-bluetooth/blob/master/pages/index.vue
			#													TYP		KEY		VAL (uint16)
			#luigi Data on Mario Events port:0x8 0x0 0x45 0x3	0x9 	0x20	0x1 0x0

			event_type = data[0]
			event_key = data[1]
			value = BTLegoMario.mario_bytes_to_int(data[2:])

			decoded_something = False
			if event_type == 0x2:
				if event_key == 0x18:
					#0x2 0x18 0x2 0x0
					#0x2 0x18 0x1 0x0
					if value == 2:
						print(self.which_brother+" fell asleep")
						decoded_something = True
					elif value == 1:
						print(self.which_brother+" woke up")
						decoded_something = True
			elif event_type == 0x1:
				if event_key == 0x18:
					if value == 0:
						# 0x1 0x18 0x0 0x0
						# Happens a little while after the flag, sometimes on bootup too
						print(self.which_brother+" course status has been reset")
						decoded_something = True

			if event_key == 0x20:
				print(self.which_brother+" now has "+str(value)+" coins (obtained via "+str(hex(event_type))+")")
					# via:
					# 0x9:	Bouncing around randomly
					# 0x42:	Goomba
					# 0x44:	Whatever complexity stomping a Spiny is
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

			# Dumped on app connect
			# 0x1 0x19 0x3 0x0
			# 0x2 0x19 0x8 0x0
			# 0x10 0x19 0x1 0x0
			# 0x11 0x19 0x7 0x0
			# 0x80 0x1 0x0 0x0
			# 0x15 0x1 0x8 0x0
			# 0x1 0x18 0x0 0x0		DONE: Course status reset
			# 0x1 0x40 0x1 0x0
			# 0x2 0x40 0x1 0x0
			# 0x1 0x30 0x0 0x0

			if not decoded_something:
				print(self.which_brother+" event data:"+" ".join(hex(n) for n in data))
		else:
			print(self.which_brother+" non-mode-2-style event data:"+" ".join(hex(n) for n in data))

		pass

	def decode_advertising_name(self, name):
		#LEGO Mario_j_r

		if name.startswith("LEGO Mario_") == False or len(name) != 14:
			print("Unusual advertising name set:"+name)
			return

		icon = ord(name[11])
		color = ord(name[13])

		color_str =  self.app_icon_color_names[color]
		icon_str =  self.app_icon_names[icon]

		print(self.which_brother+" icon is set to "+color_str+" "+icon_str)

	# ---- Utilities ----

	def get_code_info(barcode_int):
		info = {
			'id':barcode_int,
			'barcode':BTLegoMario.int_to_scanner_code(barcode_int)
		}
		if BTLegoMario.code_data:
			# print("Scanning database for code..")
			if BTLegoMario.code_data['version'] == 7:
				info = BTLegoMario.populate_code_info_version_7(info)

		if not 'label' in info:
			info['label'] = 'x_'+info['barcode']+"_"
		return info

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
					info['label'] = code['label']
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
						code = "-----\t"
					mario_hex = BTLegoMario.int_to_mario_bytes(count)
					#print(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex))
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
					#print(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex))
					BTLegoMario.br_codespace[count] = code
					count += 1

	def print_codespace():
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
			mirrorcode = None
			splitcode = c.split('\t')
			if isinstance(splitcode, list):
				c = splitcode[0]
				if splitcode[1]:
					mirrorcode = splitcode[1]
			mario_hex = BTLegoMario.int_to_mario_bytes(i)
			if mirrorcode:
				mirrorcode = c+"\t"+mirrorcode
			else:
				mirrorcode = c+"\t"
			print(str(i)+"\t"+mirrorcode+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex)+"\t"+'{:09b}'.format(i))

	# Probably useful instead of having to remember to do this when working with bluetooth
	def mario_bytes_to_int(mario_byte_array):
		return int.from_bytes(mario_byte_array, byteorder="little")

	# Not useful anywhere but here, IMO
	def int_to_mario_bytes(mario_int):
		return mario_int.to_bytes(2, byteorder="little")

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

	async def set_port_subscriptions(self, portlist):
		# array of 3-item arrays [port, mode, subscribe on/off]
		if isinstance(portlist, Iterable):
			for port_settings in portlist:
				if isinstance(port_settings, Iterable) and len(port_settings) == 3:
					await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, BTLegoMario.port_inport_format_setup_bytes(port_settings[0],port_settings[1],port_settings[2]))
					await asyncio.sleep(0.1)

	async def set_icon(self, icon, color):
		if icon not in self.app_icon_ints:
			print("ERROR: Attempted to set invalid icon:"+icon)
			return
		if color not in self.app_icon_color_ints:
			print("ERROR: Attempted to set invalid color for icon:"+color)

		set_name_bytes = bytearray([
			0x00,	# len placeholder
			0x00,	# padding but maybe stuff in the future (:
			0x1,	# 'hub_properties'
			0x1,	# 'Advertising Name'
			0x1		# 'Set'
		])

		set_name_bytes = set_name_bytes + "LEGO Mario_I_C".encode()

		set_name_bytes[0] = len(set_name_bytes)
		set_name_bytes[16] = self.app_icon_ints[icon]
		set_name_bytes[18] = self.app_icon_color_ints[color]

		#print(" ".join('0x{:02x}'.format(n) for n in set_name_bytes))

		await self.client.write_gatt_char(BTLegoMario.characteristic_uuid, set_name_bytes)
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
								print("Requesting updates for hub property: "+hub_property)
								hub_property_operation = 0x2
							else:
								print("Disabling updates for hub property: "+hub_property)
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

	def port_inport_format_setup_bytes(port, mode, enable):
		# original hint from https://github.com/salendron/pyLegoMario
		# Port Input Format Setup (Single) message

		# Sending this results in port_input_format_single response
		ebyte = 0
		if enable:
			ebyte = 1
		# Len, 0x0, Port input format (single), port, mode, delta interval of 5 (uint32), notification enable/disable
		return bytearray([0x0A, 0x00, 0x41, port, mode, 0x05, 0x00, 0x00, 0x00, ebyte])
