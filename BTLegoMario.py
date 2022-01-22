import asyncio
from bleak import BleakClient

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
# Device Capabilities: 3 (Supports central and peripheral (bitmask))
# Rest is garbage, AFAIAC

class BTLegoMario:
	connected = False

	mario_characteristic_uuid = '00001624-1212-efde-1623-785feabcd123'
	mario_hub_service_uuid = '00001623-1212-efde-1623-785feabcd123'

	# https://github.com/bricklife/LEGO-Mario-Reveng
	# Port #
	#	0: Accel
	#	1: Barcode
	#	2: Pants
	#	3: Something
	#	4: Something
	#	5: Nothing?
	#	6: Voltage

	# https://github.com/salendron/pyLegoMario
	SUBSCRIBE_IMU_COMMAND = bytearray([0x0A, 0x00, 0x41, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x01])
	SUBSCRIBE_RGB_COMMAND = bytearray([0x0A, 0x00, 0x41, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00, 0x01])

	which_brother = None
	class_device = None
	address = None
	lock = None
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

	def __init__(self):
		self.lock = asyncio.Lock()

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
		return None

	async def connect(self, device, advertisement_data):
		async with self.lock:
			self.which_brother = BTLegoMario.which_device(advertisement_data)
			print("Connecting to "+str(self.which_brother)+"...")

			try:
				async with BleakClient(device.address) as client:
					if not client.is_connected:
						print("Failed to connect after client creation")
						return
					print("Connected to "+self.which_brother+"!")
					self.connected = True

					await client.start_notify(BTLegoMario.mario_characteristic_uuid, self.mario_events)
					await asyncio.sleep(0.1)
					await client.write_gatt_char(BTLegoMario.mario_characteristic_uuid, BTLegoMario.SUBSCRIBE_IMU_COMMAND)
					await asyncio.sleep(0.1)
					await client.write_gatt_char(BTLegoMario.mario_characteristic_uuid, BTLegoMario.SUBSCRIBE_RGB_COMMAND)
					while client.is_connected:
						await asyncio.sleep(0.05)
					print(self.which_brother+" has disconnected.")
					self.connected = False

			except Exception as e:
				print("Unable to connect to "+str(device.address))
				print(e)

	def mario_events(self, sender, data):
		dtype = "IDK"
		if data[0] == 0x8:
			dtype="SCANNER"
		elif data[0] == 0x7:
			dtype="TILT"
		elif data[0] == 0xF:
			dtype="F WAT"
		elif data[0] == 0xA:
			dtype="A WAT"

		if dtype == "SCANNER":
			scantype = None
			if data[6] == 0xff and data[7] == 0xff:
				scantype = 'barcode'
			if data[4] == 0xff and data[5] == 0xff:
				if scantype == 'barcode':
					scantype = 'nothing'
				else:
					scantype = 'color'
			if not scantype:
				scantype = "UNKNOWN"
				# Happened after they connected to themselves and THEN to the computer
				#mario SCANNER UNKNOWN: 0x8 0x0 0x45 0x3 0x6e 0x38 0x0 0x0
				#luigi SCANNER UNKNOWN: 0x8 0x0 0x45 0x3 0x62 0x38 0x0 0x0
				#luigi SCANNER UNKNOWN: 0x8 0x0 0x45 0x3 0x59 0x38 0x1 0x0

			if scantype == 'barcode':
				#print(dtype+" "+scantype+": " + str(hex(data[4])) +" "+str(hex(data[5])))
				barcode_int = BTLegoMario.mario_bytes_to_int(data[4:6])
				# FIXME: Load the JSON in here and print even more useful data
				print(self.which_brother+" "+dtype+" "+scantype+": " + BTLegoMario.int_to_scanner_code(barcode_int)+ " ("+str(barcode_int)+")")
			elif scantype == 'color':
				print(self.which_brother+" "+dtype+" "+scantype+": " + BTLegoMario.mario_bytes_to_solid_color(data[6:8]))
			elif scantype == 'nothing':
				print(self.which_brother+" "+dtype+" "+scantype)
			else:
				print(self.which_brother+" "+dtype+" "+scantype+": " + " ".join(hex(n) for n in data))

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
			print(str(i)+"\t"+mirrorcode+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex))

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
