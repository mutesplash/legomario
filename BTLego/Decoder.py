from binascii import hexlify
import struct	# bin to FP32
import importlib
from enum import IntEnum

# Hub properties (hub_property_str indicies)
class HProp(IntEnum):
	AD_NAME = 0x1
	BUTTON = 0x2
	FIRMWARE = 0x3
	HARDWARE = 0x4
	RSSI = 0x5
	BATT = 0x6
	BATT_TYPE = 0x7
	MANUF_NAME = 0x8
	RADIO_FW = 0x9
	LWPVER = 0xa
	SYSTYPE = 0xb
	HWNET = 0xc
	MAC = 0xd
	MAC2 = 0xe
	NW_FAM = 0xf
	MARIO_VOLUME = 0x12

# LPF2-compatible devices (io_type_id_str indicies)
class LDev(IntEnum):
	MOTOR = 0x1
	TRAIN = 0x2
	# 0x5:'Button',	# Where did you get this from??
	LED = 0x8
	VOLTS = 0x14
	CURRENT = 0x15
	# 0x16:'Piezo Tone',
	RGB = 0x17
	# 0x21:'Powered Up Hub battery current'
	TILT = 0x22
	MOTION = 0x23
	VISION = 0x25
	MOTOR_BOOST = 0x26
	MOTOR_BOOST_INTERNAL = 0x27
	BOOST_TILT = 0x28
	DUPLO_MOTOR = 0x29
	DUPLO_BEEPER = 0x2a
	DUPLO_COLOR = 0x2b
	DUPLO_SPEED = 0x2c
	CONTROLPLUS_LARGE = 0x2e
	CONTROLPLUS_XL = 0x2f
	MOTOR_M_B = 0x30
	MOTOR_L_B = 0x31
	IMU_GEST = 0x36		# Powered Up hub IMU gesture',
	CONTROL_BUTTON = 0x37
	BT_RSSI = 0x38		# 'Powered Up hub Bluetooth RSSI'	88010 also has this
	IMU_ACCEL = 0x39	# 'Powered Up hub IMU accelerometer'
	IMU_GYRO = 0x3a		# 'Powered Up hub IMU gyro'
	IMU_POS	= 0x3b		# 'Powered Up hub IMU position'
	TEMP = 0x3c			# 'Powered Up hub IMU temperature'
	COLOR = 0x3d
	ULTRA = 0x3e
	FORCE = 0x3f
	MATRIX = 0x40
	MOTOR_S = 0x41
	# 0x42: Useless turtle, do not enable unless it becomes not-useless
	EVENTS = 0x46		# Mario and Controller
	MARIO_TILT = 0x47
	MARIO_SCANNER = 0x49	# Aka LEAFTag ?
	MARIO_PANTS = 0x4a
	MOTOR_M_G = 0x4b
	MOTOR_L_G = 0x4c
	MARIO_ALT = 0x55	# 'Mario Alt Events'
	MOTOR_PLAYVM = 0x56
	MOTOR_PLAYVM_STEER = 0x57
	SIX_LED = 0x58


# FIXME: Completely confused on upstream/downstream, fix the nomenclature in the comments

class Decoder():

	# One of the few ways to identify this device
	WEDO2_SERVICE_UUID = '00001523-1212-efde-1523-785feabcd123'

	advertised_system_type = {
		# 0x0: Things that don't have an advertised system type: 'wedo2'
		0x20:'duplotrain',	# "Hub No. 5" "Train Base"
		0x40:'boostmove',	# "JAJUR1" "LEGO Move Hub" "LEGO® Powered Up 88006 Move Hub" The set this hub comes in (17101) is called "Boost"
		0x41:'hub_4',		# Lego 88009 Powered Up "Hub", "HUB NO.4"
		0x42:'handset',		# Lego 88010 Remote Control for Powered Up
		0x43:'mario',
		0x44:'luigi',
		0x45:'peach',
		0x60:'smartbrick',	# "SMART Brick" Uses WDX proto, not LWP. Check out this hero: https://github.com/nathankellenicki/node-smartplay/blob/main/notes/PROTOCOL.md
		0x80:'hub_2',		# "Hub No. 2" Lego 88012, Default name of "Technic Hub", "LEGO Powered Up Technic Hub"
		0x83:'spikesmall',	# "Hub No. 7"
		0x84:'technicmove'
	}

	ble_dev_classes = {
		0x20:'DuploTrain',
		0x40:'Jajur1',
		0x41:'Hub4',
		0x42:'Controller',
		0x43:'Mario',
		0x44:'Mario',		# Luigi
		0x45:'Mario',		# Peach
		0x60:'BLE_Smartbrick',
		0x80:'Hub2',
		0x83:'SpikeEssential',
		0x84:'Hub19'	# Identifies itself as "Technic Move  "
	}

	#https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#message-typ
	message_type_ints = {}
	message_type_str = {
		0x1:"hub_properties",
		0x2:"hub_actions",
		0x3:"hub_alerts",
		0x4:"hub_attached_io",
		0x5:"generic_error",
		0x8:"hw_network_cmd",
		0x10:"firmware_update_bootmode",
		0x11:"firmware_update_lockmem",
		0x12:"firmware_update_lockstat",
		0x13:"firmmware_lockstat",
		0x21:"port_info_req",
		0x22:"port_mode_info_req",
		0x41:"port_input_format_setup_single",
		0x42:"port_input_format_setup_combi",
		0x43:"port_info",
		0x44:"port_mode_info",
		0x45:"port_value_single",
		0x46:"port_value_combi",
		0x47:"port_input_format_single",
		0x48:"port_input_format_combi",
		0x61:"virtual_port_setup",
		0x81:"port_output_command",
		0x82:"port_output_command_feedback"
	}

	mode_info_type_str = {
		0x0:'NAME',
		0x1:'RAW',
		0x2:'PCT',
		0x3:'SI',
		0x4:'SYMBOL',
		0x5:'MAPPING',
		0x6:'__INTERNAL',
		0x7:'__MOTOR_BIAS',
		0x8:'__CAPABILITY_BITS',
		0x80:'VALUE_FORMAT'
	}

	io_event_type_str = {
		0x0: 'detached',
		0x1: 'attached',
		0x2: 'attached_virtual'
	}

	io_type_id_str = {
		# Lego BT document names
		# Pybricks documents this space too https://github.com/pybricks/technical-info/blob/master/assigned-numbers.md#io-device-type-ids
		0x1:'Motor',
		0x2:'System Train Motor',
		0x5:'Button',
		0x8:'LED Light',
		0x14:'Voltage',
		0x15:'Current',
		0x16:'Piezo Tone',
		0x17:'RGB Light',
		0x21:'Powered Up Hub battery current',
		0x22:'External Tilt Sensor',
		0x23:'Motion Sensor',
		0x25:'Vision Sensor',
		0x26:'External Motor with Tacho',	# BOOST Interactive Motor
		0x27:'Internal Motor with Tacho',	# BOOST Motor Built-in to Move hub
		0x28:'Internal Tilt',
		0x29:'DUPLO Train hub built-in motor',
		0x2a:'DUPLO Train hub built-in beeper',
		0x2b:'DUPLO Train hub built-in color sensor',
		0x2c:'DUPLO Train hub built-in speed',
		0x2e:'Technic Control+ Large Motor',
		0x2f:'Technic Control+ XL Motor',

		# Pybricks
		0x30:'SPIKE Prime Medium Motor',		# Medium Azure color
		0x31:'SPIKE Prime Large Motor',			# Medium Azure color
		0x36:'Powered Up hub IMU gesture',
		0x37:'Powered Up Handset Buttons',
		0x38:'Powered Up hub Bluetooth RSSI',	# 88010 also has this
		0x39:'Powered Up hub IMU accelerometer',
		0x3a:'Powered Up hub IMU gyro',
		0x3b:'Powered Up hub IMU position',
		0x3c:'Powered Up hub IMU temperature',
		0x3d:'Technic Color Sensor',
		0x3e:'Technic Ultrasonic/Distance Sensor',
		0x3f:'Technic Force Sensor',
		0x40:'Matrix',	# FIXME: Not coordinated with pybricks...
		0x41:'Technic Small Angular Motor',
		0x42:'Useless BOOST Turtle',			# Device is not useful and is labeled NO IO
		0x4b:'Technic Medium Angular Motor',	# Gray color
		0x4c:'Technic Large Angular motor',		# Gray color

		0x4e:'UNKNOWN SPIKE Essential device',	# A NO-IO device according to its probe

		# My names
		0x46:'LEGO Events',			# Events from 88010 Powered Up controller and LEGO Mario
		0x47:'Mario Tilt Sensor',	# aka IMU
		0x49:'Mario RGB Scanner',	# The code & color scanner
		0x4a:'Mario Pants Sensor',
		0x55:'Mario Alt Events',

		0x56:'Technic Move Motor',
		0x57:'Technic Move Steering Motor',
		0x58:'Technic Move Six-LED Control',
		0x59:'UNKNOWN TECHNIC 89 PLAYVM DEVICE',

		0x5c:'IDK PlayVM Events Maybe???',
		0x5d:'Technic Move Orientation Sensor',
		0x5e:'UNKNOWN TECHNIC 94 GESTURE DEVICE',
		0x5f:'UNKNOWN TECHNIC 95 GESTURE DEVICE',

		0x60:'Mario Telemetry'
	}

	hub_alert_type_str = {
		0x1:'Low Voltage',
		0x2:'High Current',
		0x3:'Low Signal Strength',
		0x4:'Over Power Condition'
	}

	hub_alert_op_str = {
		0x1:'Enable Updates',	# Downstream (write to BT device)
		0x2:'Disable Updates',	# Downstream
		0x3:'Request Updates',	# Downstream
		0x4:'Update'			# Upstream (emitted from BT device)
	}

	hub_property_ints = {}
	hub_property_str = {
		0x1:'Advertising Name',
		0x2:'Button',
		0x3:'FW Version',
		0x4:'HW Version',
		0x5:'RSSI',
		0x6:'Battery Voltage',	# Seems to actually be percentage?
		0x7:'Battery Type',
		0x8:'Manufacturer Name',
		0x9:'Radio Firmware Version',
		0xa:'LEGO Wireless Protocol Version',
		0xb:'System Type ID',
		0xc:'H/W Network ID',
		0xd:'Primary MAC Address',
		0xe:'Secondary MAC Address',
		0xf:'Hardware Network Family',

		# My name
		0x12:'Mario Volume',	# Can't enable updates on this property, which is annoying.
								# Also won't send an Update when you Set it
								# Valid Set values: 0 - 100
								# The levels in the app are 100, 90, 75, 50, 0
								# Which is weird, but whatever

		# Fuzzed hub2, hub4, controller, boostmove, peach, and duplotrain from 16 to 255 all to find only this
		# Shows up on mario, hub2, spikesmall
		0x13:'Mario_UNKNOWN'	# Payload of 0x0 0x0 0x0 0x22

	}

	hub_properties_that_update = [
		0x1,	# Advertising Name
		0x2,	# Button
		0x5,	# RSSI
		0x6		# Voltage
	]

	hub_property_op_str = {
		0x1:'Set',				# Downstream  (write to BT device)
		0x2:'Enable Updates',	# Downstream
		0x3:'Disable Updates',	# Downstream
		0x4:'Reset',			# Downstream
		0x5:'Request Update',	# Downstream
		0x6:'Update'			# Upstream
	}

	hub_action_type = {
		# Downstream
		0x1:'Switch Off Hub',
		0x2:'Disconnect',
		0x3:'VCC Port Control On',
		0x4:'VCC Port Control Off',
		0x5:'Active Busy',
		0x6:'Reset Busy',
		0x2F:'Shutdown',		# Fast powerdown, no messages

		# Upstream
		0x30:'Hub Will Switch Off',
		0x31:'Hub Will Disconnect',
		0x32:'Hub Will Go Into Boot Mode'
	}

	# LWP 3.9
	generic_errors = {
		0x1:'ACK',
		0x2:'Multiple ACK',
		0x3:'Buffer Overflow',
		0x4:'Timeout',
		0x5:'Command was not recognized',
		0x6:'Invalid use of command',
		0x7:'Overcurrent',
		0x8:'Internal Error'
	}

	hw_network_command_type = {
		0x2:'Connection Request',
		0x3:'Family Request [New family if available]',
		0x4:'Family Set',
		0x5:'Join Denied',
		0x6:'Get Family',
		0x7:'Family',
		0x8:'Get SubFamily',
		0x9:'SubFamily',
		0xA:'SubFamily Set',
		0xB:'Get Extended Family',
		0xC:'Extended Family',
		0xD:'Extended Family Set',
		0xE:'Reset Long Press Timing'
	}

	rgb_light_colors = {
		0x0:'none',
		0x1:'pink',
		0x2:'lilac',
		0x3:'blue',
		0x4:'cyan',
		0x5:'turquoise',
		0x6:'green',
		0x7:'yellow',
		0x8:'orange',
		0x9:'red',
		0xa:'white'
	}

	# https://github.com/nathankellenicki/node-smartplay/blob/main/notes/PROTOCOL.md
	wdx_registers = {
		0x01:('ConnectionParameterUpdateReq','W'),
		0x02:('CurrentConnectionParameters','R'),
		0x03:('DisconnectReq','W'),
		0x04:('ConnectionSecurityLevel','R'),
		0x05:('SecurityReq','W'),
		0x06:('ServiceChanged','R'),
		0x07:('DeleteBonds','W'),
		0x08:('CurrentAttMtu','R'),
		0x09:('PhyUpdateReq','W'),
		0x0a:('CurrentPhy','R'),

		0x20:('BatteryLevel','R'),
		0x21:('DeviceModel','R'),
		0x22:('FirmwareRevision','R'),
		0x23:('EnterDiagnosticMode','W'),
		0x24:('DiagnosticModeComplete','R'),
		0x25:('DisconnectAndReset','W'),
		0x26:('DisconnectConfigureFotaAndReset','W'),

		0x80:('HubLocalName','RW'),
		0x81:('UserVolume','RW'),
		0x82:('CurrentWriteOffset','R'),
		0x83:('FIXME_UNKNOWN_1',''),
		0x84:('PrimaryMacAddress','R'),
		0x85:('UpgradeState','R'),
		0x86:('SignedCommandNonce','R'),
		0x87:('SignedCommand','W'),
		0x88:('UpdateState','R'),
		0x89:('PipelineStage','R'),
		0x90:('UXSignal','W'),
		0x91:('OwnershipProof','W'),
		0x92:('FIXME_UNKNOWN_2',''),
		0x93:('ChargingState','R'),
		0x94:('FIXME_UNKNOWN_3',''),
		0x95:('FactoryReset','W'),
		0x96:('TravelMode','RW'),
	}

	wdx_message_types = {
		1:'read',
		2:'write',
		3:'response'
	}

#	def __init__(self):
		# reverse map some dicts so you can index them either way
#		self.message_type_ints = dict(map(reversed, self.message_type_str.items()))
#		self.hub_property_ints = dict(map(reversed, self.hub_property_str.items()))
#		pass

	message_type_ints = dict(map(reversed, message_type_str.items()))
	hub_property_ints = dict(map(reversed, hub_property_str.items()))
	io_type_id_ints = dict(map(reversed, io_type_id_str.items()))

	def classname_from_ad_data(advertisement_data):
		classname = None
		if 919 in advertisement_data.manufacturer_data:
			type_id = advertisement_data.manufacturer_data[919][1]
			classname = 'BLE_Device'

			if type_id in Decoder.ble_dev_classes:
				classname = Decoder.ble_dev_classes[type_id]

		if advertisement_data.service_uuids:
			if Decoder.WEDO2_SERVICE_UUID in advertisement_data.service_uuids:
				classname = 'BLE_WeDo'
		return classname

	def class_obj_from_classname(classname):
		if classname:
			class_module = importlib.import_module(f'BTLego.{classname}')
			classobj = getattr(class_module, classname)
			return classobj
		return None

	def determine_device_shortname(advertisement_data):
		systype = Decoder.determine_device_systemtype(advertisement_data)
		if systype in Decoder.advertised_system_type:
			# print("Dumping LEGO Manuf. ID advertisement data:"+" ".join(hex(n) for n in advertisement_data.manufacturer_data[919]))
			return Decoder.advertised_system_type[systype]
		else:
			return 'UNKNOWN_LEGO_'+hex(systype)

	def determine_device_systemtype(advertisement_data):
		# https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#document-2-Advertising
		# kCBAdvDataManufacturerData = 0x9703004403ffff00
		# 97 03 is backwards because it's supposed to be a 16 bit int
		# 919 aka 0x397 or the lego manufacturer id (Bluetooth SIG "Assigned Numbers" document)

		if 919 in advertisement_data.manufacturer_data:
			# 004403ffff00
			# 00 Button state
			# 44 System type (44 for luigi, 43 mario)
			#	0x44 010 00100	System type 010 (Lego system), Device number(IDK)
			#	0x43 010 00011
			# Device Number 3 & 4: mario... what about the Mindstorms hub?
			# 03 Capabilites
			#	0000 0011
			#	       01	Central role
			#          10	Peripheral role
			# ff Last network ID (FF is not implemented)
			# ff Status (I can be everything)
			# 00 Option (unused)

			# Train
			# 0x0 0x20 0x2 0xfe 0x41 0x0
			# 02 Capabilities
			#	0000 0010
			#          10	Peripheral role

			# SMART Brick only has System type set, zeroes out everything else (Does respect length of 6)

			return advertisement_data.manufacturer_data[919][1]

		else:
			# Fun for finding everything else
			#print(advertisement_data)
			pass
		return 0x0

	def device_info_from_ad_data(advertisement_data):
		classname = Decoder.classname_from_ad_data(advertisement_data)
		retval = {
			'systype': Decoder.determine_device_systemtype(advertisement_data),
			'class': Decoder.class_obj_from_classname(classname),
			'shortname': Decoder.determine_device_shortname(advertisement_data)
		}

		if retval['systype'] == 0x0 and classname == 'BLE_WeDo':
			retval['shortname'] = 'wedo2'

		return retval

	def decode_payload(message_bytes, source_char_uuid):
		bt_message = {
			'char_uuid': source_char_uuid,
			'error': False,
			'raw':message_bytes
		}
		# FIXME: Doesn't detect lengths over 127
		# https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#message-length-encoding
		length = message_bytes[0]
		unused_hub_id = message_bytes[1]
		if len(message_bytes) != length:
			bt_message['error'] = True
			bt_message['readable'] = "CORRUPTED MESSAGE: stated len "+str(length)+" != "+str(len(message_bytes))+" "+" ".join(hex(n) for n in message_bytes)+" "
			# Don't return, attempt to decode, since error flag set
		else:
			bt_message['readable'] = ''
		bt_message['type']  = message_bytes[2]
		bt_message['readable'] += Decoder.int8_dict_to_str(Decoder.message_type_str, bt_message['type']) + " - "

		if bt_message['type'] == 0x1:
			Decoder.decode_hub_properties(bt_message)
		elif bt_message['type'] == 0x2:
			Decoder.decode_hub_action(bt_message)
		elif bt_message['type'] == 0x3:
			Decoder.decode_hub_alert(bt_message)
		elif bt_message['type'] == 0x4:
			Decoder.decode_hub_attached_io(bt_message)
		elif bt_message['type'] == 0x5:
			Decoder.decode_generic_error(bt_message)
		elif bt_message['type'] == 0x8:
			Decoder.decode_hw_network_command(bt_message)


		# Undocumented mario messages
		#elif bt_message['type'] == 0x7:
		#elif bt_message['type'] == 0xb:

		elif bt_message['type'] == 0x43:
			Decoder.decode_port_mode_info(bt_message)
		elif bt_message['type'] == 0x44:
			Decoder.decode_port_mode_info_request(bt_message)
		elif bt_message['type'] == 0x45:
			Decoder.decode_port_value_single(bt_message)
		elif bt_message['type'] == 0x47:
			Decoder.decode_port_input_format_single(bt_message)
		elif bt_message['type'] == 0x82:
			Decoder.decode_port_output_command_feedback(bt_message)
		else:
			bt_message['error'] = True
			bt_message['readable'] += "No decoder for message: "+" ".join(hex(n) for n in message_bytes)

		return bt_message

	def decode_hub_action(bt_message):
		if len(bt_message['raw']) != 4:
			bt_message['readable'] += "CORRUPTED MESSAGE: mesage len "+str(len(bt_message['raw']))+" is wrong for a hub action: "+" ".join(hex(n) for n in bt_message['raw'])
			bt_message['error'] = True
			return

		bt_message['action'] = bt_message['raw'][3]
		bt_message['action_str'] = Decoder.int8_dict_to_str(Decoder.hub_action_type, bt_message['action'])
		bt_message['readable'] += "Hub action "+hex(bt_message['raw'][3])+ ":"+bt_message['action_str']

	def decode_port_output_command_feedback(bt_message):
		payload = bt_message['raw'][3:]
		# 0x5 0x0 0x82 [0x4 0xa]
		if len(payload) % 2 != 0:
			bt_message['readable'] += "CORRUPTED MESSAGE: length of payload "+str(len(payload))+" is not divisible by 2: "+" ".join(hex(n) for n in payload)
			return
		portcount = len(payload) / 2
		retval = ""
		bt_message['ports'] = []
		for p in range(0, len(payload), 2):
			bt_message['ports'].append({})
			bt_message['ports'][p]['id'] = payload[p]

			port_feedback_bitfield = payload[p+1]
			port_feedback = ""
			if port_feedback_bitfield & 0x1:
				port_feedback += " Empty&InProgress"
			if port_feedback_bitfield & 0x2:
				port_feedback += " Empty&Completed"
			if port_feedback_bitfield & 0x4:
				port_feedback += " Discarded"
			if port_feedback_bitfield & 0x8:
				port_feedback += " Idle"
			if port_feedback_bitfield & 0x10:
				port_feedback += " Busy/Full"

			if not port_feedback:
				port_feedback = "(None)"
				bt_message['ports'][p]['readable'] = ""
			else:
				bt_message['ports'][p]['readable'] = port_feedback
			retval += "port:"+str(bt_message['ports'][p]['id'])+" feedback:"+port_feedback+" "
		bt_message['readable'] += retval

	def decode_hub_properties(bt_message):
		# 0x9 0x0 0x1 [ 0x3 0x6 0x0 0x0 0x3 0x51 ]
		payload = bt_message['raw'][3:]
		length = len(bt_message['raw'])

		property_involved = payload[0]
		bt_message['property'] = property_involved
		property_involved_str = Decoder.int8_dict_to_str(Decoder.hub_property_str, property_involved)

		bt_message['operation'] = payload[1]
		property_operation_str = Decoder.int8_dict_to_str(Decoder.hub_property_op_str, payload[1])

		# 0x9 0x0 0x1 0x3 0x6 [ 0x0 0x0 0x3 0x51 ]
		# FIXME: Incomplete
			#0xb:'System Type ID',
			#0xc:'H/W Network ID',
			#0xe:'Secondary MAC Address',
			#0xf:'Hardware Network Family'

		property_value = f'IDK_WAT {property_involved_str}'
		bt_message['value'] = property_value

		# 'Advertising Name'
		if property_involved == 0x1:
			property_value = bytearray(payload[2:]).decode()
			bt_message['value'] = property_value

		# 'Button'
		elif property_involved == 0x2:
			# 5 + 1
			if length != 6:
				bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a boolean hub property: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
				return
			if payload[2]:
				property_value = "TRUE"
				bt_message['value'] = True
			else:
				property_value = "FALSE"
				bt_message['value'] = False

		# 'FW Version'
		elif property_involved == 0x3:
			# 5 + 4
			if length != 9:
				bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a uint32 hub property: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
				return
			property_value = Decoder.version_bytes_to_str(payload[2:])
			bt_message['value'] = property_value

		# 'HW Version'
		elif property_involved == 0x4:
			if length != 9:
				bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a uint32 hub property: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
				return
			property_value = Decoder.version_bytes_to_str(payload[2:])
			bt_message['value'] = property_value

		# 'RSSI'
		elif property_involved == 0x5:
			if length != 6:
				bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a uint8 hub property: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
				return
			property_value = str(int(payload[2]))
			bt_message['value'] = int(payload[2])

		# 'Battery Voltage'
		elif property_involved == 0x6:
			if length != 6:
				return "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a uint8 hub property: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
			bt_message['value'] = int(payload[2])
			property_value = str(bt_message['value'])+"%"

		# 'Battery Type'
		elif property_involved == 0x7:
			if length != 6:
				bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a boolean hub property: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
				return
			if payload[2]:
				property_value = "Rechargeable"
			else:
				property_value = "Normal (Disposeable)"
			bt_message['value'] = property_value

		# 'Manufacturer Name'
		elif property_involved == 0x8:
			# Won't work correctly on big-endian machines
			property_value = bytearray(payload[2:]).decode()
			bt_message['value'] = property_value

		# 'Radio Firmware Version'
		elif property_involved == 0x9:
			property_value = bytearray(payload[2:]).decode()
			bt_message['value'] = property_value

		#'LEGO Wireless Protocol Version'
		elif property_involved == 0xa:
			if length != 7:
				bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a uint16 hub property: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
				return
			bt_message['value'] = Decoder.uint16_bytes_to_int(payload[2:])
			property_value = str(bt_message['value'])

		# 'Primary MAC Address'
		elif property_involved == 0xd:
			# 5 + 6
			if length != 11:
				bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a MAC address property: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
				return
			property_value = ":".join(hexlify(n.to_bytes(1,byteorder='little')).decode('ascii') for n in payload[2:])
			bt_message['value'] = property_value

		# Mario Volume
		elif property_involved == 0x12:
			if payload[1] != 0x6:
				bt_message['readable'] += "UNKNOWN VOLUME PREFIX IN MESSAGE: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
				return

			property_value = str(int(payload[2]))
			# 0 - 100
			bt_message['value'] = int(payload[2])

		else:
			bt_message['readable'] += property_involved_str+" "+property_operation_str+" UNKNOWN remaining payload:"+" ".join(hex(n) for n in payload[2:])
			return

		bt_message['readable'] += property_involved_str+" "+property_operation_str+": "+property_value

	def decode_hub_alert(bt_message):
		#0x6 0x0 0x3 [ 0x2 0x4 0x0 ]
		payload = bt_message['raw'][3:]

		bt_message['alert_type'] = payload[0]
		bt_message['operation'] = payload[1]

		# Only "downstream" has boolean "alert payload"
		status = "OK"
		bt_message['status'] = False
		if payload[2] == 0xff:
			status = "ALERT!"
			bt_message['status'] = True
			bt_message['alert_type_str'] = Decoder.int8_dict_to_str(Decoder.hub_alert_type_str, payload[0])
			bt_message['operation_str'] = Decoder.int8_dict_to_str(Decoder.hub_alert_op_str, payload[1])
			bt_message['readable'] += f"Alert Status: {status} : type {bt_message['alert_type_str']} operation {bt_message['operation_str']}"
		else:
			bt_message['readable'] += f"Alert Status: {status}"

	def decode_port_input_format_single(bt_message):
		payload = bt_message['raw'][3:]
		bt_message['port'] = payload[0]
		bt_message['mode'] = payload[1]
		bt_message['delta'] = int.from_bytes(payload[2:6], byteorder="little", signed=False)
		notifications = " Notifications disabled"
		bt_message['notifications'] = False
		if ( payload[6] ):
			notifications = " Notifications enabled"
			bt_message['notifications'] = True
		bt_message['readable'] += "port "+str(bt_message['port'])+" mode " + str(bt_message['mode']) + " delta interval for jitter filtering:"+str(bt_message['delta'])+notifications

	def decode_hub_attached_io(bt_message):
		payload = bt_message['raw'][3:]
		io_size_indicator = len(bt_message['raw'])

		# 0xf 0x0 0x4 [ 0x0 0x1 0x47 0x0 0x0 0x0 0x3 0x51 0x1 0x0 0x0 0x0 ]
		iotype = None
		port = payload[0]
		bt_message['port'] = port
		event = Decoder.int8_dict_to_str(Decoder.io_event_type_str,payload[1])
		bt_message['event'] = payload[1]
		# --- --- --- 0x0 0x1 [0x47 0x0 0x0 0x0 0x3 0x51 0x1 0x0 0x0 0x0 ]
		# attached
		if io_size_indicator == 15:
			bt_message['io_type_id'] = Decoder.uint16_bytes_to_int(payload[2:4])
			hw_rev = Decoder.version_bytes_to_str(payload[4:8])
			bt_message['hw_ver_str'] = hw_rev
			sw_rev = Decoder.version_bytes_to_str(payload[8:12])
			bt_message['sw_ver_str'] = sw_rev
			bt_message['readable'] += "port "+str(port)+" "+event+" IOTypeID:"+str(bt_message['io_type_id'])+" hw:"+hw_rev+" sw:"+sw_rev
		# attached_virtual
		elif io_size_indicator == 9:
			iotype = 'virtual_attached'
			bt_message['io_type_id'] = Decoder.uint16_bytes_to_int(payload[2:4])
			port_a = payload[4]
			bt_message['virt_a'] = port_a
			port_b = payload[5]
			bt_message['virt_b'] = port_b
			bt_message['readable'] += "port "+str(port)+" "+event+" IOTypeID:"+str(bt_message['io_type_id'])+" Port A:"+str(port_a)+" Port B:"+str(port_b)
		#  detached
		elif io_size_indicator == 5:
			# no more bytes to deal with!
			bt_message['readable'] += "port "+str(port)+" "+event
		else:
			bt_message['error'] = True
			bt_message['readable'] += "INVALID IO LENGTH ("+str(io_size_indicator)+"):  "+" ".join(hex(n) for n in payload)

	def decode_generic_error(bt_message):
		if len(bt_message['raw']) != 5:
			bt_message['readable'] += "CORRUPTED MESSAGE: message len "+str(len(bt_message['raw']))+" is wrong for a hub error: "+" ".join(hex(n) for n in bt_message['raw'])
			bt_message['error'] = True
			return

		bt_message['error'] = True
		error_cause = bt_message['raw'][3]
		error_code = bt_message['raw'][4]
		readable = hex(error_code)
		if error_code in Decoder.generic_errors:
			readable = Decoder.generic_errors[error_code]
		if error_cause in Decoder.message_type_str:
			error_cause = Decoder.message_type_str[error_cause]
		else:
			error_cause = hex(error_cause)
		bt_message['readable'] += "Command "+error_cause+" caused error: "+readable

	def decode_hw_network_command(bt_message):
		if len(bt_message['raw']) != 5 and len(bt_message['raw']) != 4:
			bt_message['readable'] += "CORRUPTED MESSAGE: message len "+str(len(bt_message['raw']))+" is wrong for a hw network command (4 or 5): "+" ".join(hex(n) for n in bt_message['raw'])
			bt_message['error'] = True
			return
		payload = bt_message['raw'][3:]

		command_token = payload[0]
		if command_token in Decoder.hw_network_command_type:
			bt_message['readable'] += " command: "+Decoder.hw_network_command_type[command_token]

		# Connection Request
		if command_token == 0x2:
			# Button State
			if payload[1] == 0x0:
				bt_message['readable'] += ": Button Released"
				bt_message['command'] = "connection_request"
				bt_message['value'] = "button_up"
			elif payload[1] == 0x1:
				bt_message['readable'] += ": Button Pressed"
				bt_message['command'] = "connection_request"
				bt_message['value'] = "button_down"
			else:
				bt_message['error'] = True
				bt_message['readable'] += ": INVALID BUTTON STATE "+hex(payload[1])
		# Family Request
		elif command_token == 0x3:
			# This doesn't have a payload
			# It also only sends after button_up AND if it has been less than _about_ 2.5 seconds
			# So, only sent on relatively quick tap of the pairing button
			bt_message['command'] = "family_request"
		else:
			bt_message['readable'] += " hw command payload: "+" ".join(hex(n) for n in payload)

	def decode_port_mode_info(bt_message):
		#0x8 0x0 0x43 [ 0x0 0x0 0x5 0x84 0x0 ]
		payload = bt_message['raw'][3:]
		bt_message['readable'] += "port "+str(payload[0])
		bt_message['port'] = payload[0]

		# Mode info
		if payload[1] == 0x1:
			#bt_message['readable'] += " mode info: "+" ".join(hex(n) for n in payload[2:])
			bt_message['num_modes'] = payload[3]
			bt_message['port_mode_capabilities'] = {
			}
			if payload[2] & 1:
				bt_message['port_mode_capabilities']['output'] = True
			else:
				bt_message['port_mode_capabilities']['output'] = False

			if payload[2] & 2:
				bt_message['port_mode_capabilities']['input'] = True
			else:
				bt_message['port_mode_capabilities']['input'] = False

			if payload[2] & 4:
				bt_message['port_mode_capabilities']['logic_combineable'] = True
			else:
				bt_message['port_mode_capabilities']['logic_combineable'] = False

			if payload[2] & 8:
				bt_message['port_mode_capabilities']['logic_synchronizeable'] = True
			else:
				bt_message['port_mode_capabilities']['logic_synchronizeable'] = False

			bt_message['readable'] += " capabilities: "+hex(payload[2])
			bt_message['readable'] += " mode count: "+str(bt_message['num_modes'])
			input_bitfield = Decoder.uint16_bytes_to_int(payload[4:6])
			output_bitfield = Decoder.uint16_bytes_to_int(payload[6:8])
			bt_message['readable'] += " input modes available (bitmask): "+str(input_bitfield)
			bt_message['readable'] += " output modes available (bitmask): "+str(output_bitfield)
			bt_message['input_bitfield'] = input_bitfield
			bt_message['output_bitfield'] = output_bitfield

		# Mode combinations
		elif payload[1] == 0x2:
			combi_modes = payload[2:]
			combi_count = len(combi_modes) / 2
			combi_index = 0
			if combi_count >= 1:
				bt_message['readable'] += " mode combinations: "
				while combi_index < combi_count:
					combi_value = Decoder.uint16_bytes_to_int(combi_modes[combi_index:2])

					modes_in_combi = []
					bit_value = 1
					mode_number = 0
					while mode_number < 16:
						if combi_value & bit_value:
							modes_in_combi.append(mode_number)
						bit_value <<=1
						mode_number += 1

					if not 'mode_combinations' in bt_message:
						bt_message['mode_combinations'] = {}
					bt_message['mode_combinations'][combi_index] = tuple(modes_in_combi)

					bt_message['readable'] += f'Combination {combi_index}: {combi_value:016b}'
					combi_index += 1
			else:
				if len(combi_modes) > 0:
					bt_message['readable'] += " Undecipherable combi mode information:"+" ".join(hex(n) for n in combi_modes)
				else:
					bt_message['readable'] += " Mode has no combos"

	def decode_port_mode_info_request(bt_message):
		#0x8 0x0 0x44 [ 0x0 0x0 0x5 0x84 0x0 ]
		payload = bt_message['raw'][3:]

		port = payload[0]
		bt_message['port'] = port

		mode = payload[1]
		bt_message['mode'] = mode

		mode_info_type = payload[2]
		bt_message['mode_info_type'] = mode_info_type

		#0x8 0x0 0x44 0x0 0x0 0x5 [ 0x84 0x0 ]
		bt_message['payload'] = payload[3:]

		#luigi port_mode_info port 0 mode 0 infotype: NAME0x52: 0x41: 0x57: 0x0: 0x0: 0x0: 0x0: 0x0: 0x0: 0x0: 0x0
		#luigi port_mode_info port 0 mode 0 infotype: RAW0x0: 0x0: 0x0: 0x0: 0x0: 0x0: 0xc8: 0x42
		#luigi port_mode_info port 0 mode 0 infotype: PCT0x0: 0x0: 0x0: 0x0: 0x0: 0x0: 0xc8: 0x42
		#luigi port_mode_info port 0 mode 0 infotype: SI0x0: 0x0: 0x0: 0x0: 0x0: 0x0: 0xc8: 0x42
		#luigi port_mode_info port 0 mode 0 infotype: SYMBOL0x63: 0x6e: 0x74: 0x0
		#luigi port_mode_info port 0 mode 0 infotype: MAPPING0x84: 0x0
		#luigi port_mode_info port 0 mode 0 infotype: VALUE_FORMAT0x3: 0x0: 0x3: 0x0

		bt_message['readable'] += "port "+str(port)+" mode " + str(mode) + " infotype: " + Decoder.int8_dict_to_str(Decoder.mode_info_type_str,mode_info_type) + " "
		if mode_info_type == 0x0:
			# NAME
			bt_message['name'] = Decoder.string_and_strip_trailing_null(payload[3:])
			bt_message['readable'] += bt_message['name']
		# Assuming this is FP32 for FLOAT
		elif mode_info_type == 0x1:
			# RAW
			bt_message['readable'] += ' Min:'+' '.join(hex(n) for n in payload[3:7])+' Max:'+' '.join(hex(n) for n in payload[7:11])
			bt_message['raw'] = {}
			bt_message['raw']['min'] = struct.unpack('f', payload[3:7])[0]
			bt_message['raw']['max'] = struct.unpack('f', payload[7:11])[0]
		elif mode_info_type == 0x2:
			# PCT (Percentage)
			bt_message['readable'] += ' Min:'+' '.join(hex(n) for n in payload[3:7])+' Max:'+' '.join(hex(n) for n in payload[7:11])
			bt_message['pct'] = {}
			bt_message['pct']['min'] = struct.unpack('f', payload[3:7])[0]
			bt_message['pct']['max'] = struct.unpack('f', payload[7:11])[0]
		elif mode_info_type == 0x3:
			# SI (?Systeme International?)
			bt_message['readable'] += ' Min:'+' '.join(hex(n) for n in payload[3:7])+' Max:'+' '.join(hex(n) for n in payload[7:11])
			bt_message['si'] = {}
			bt_message['si']['min'] = struct.unpack('f', payload[3:7])[0]
			bt_message['si']['max'] = struct.unpack('f', payload[7:11])[0]
		elif mode_info_type == 0x4:
			# SYMBOL
			bt_message['symbol'] = Decoder.string_and_strip_trailing_null(payload[3:])
			if bt_message['symbol'] == None:
				bt_message['symbol'] = 'ERR_NO_SYMBOL_FOR_PORT'

			bt_message['readable'] += bt_message['symbol']

		elif mode_info_type == 0x5:
			# Mapping, 16 bits
			# IN as in to read-IN, OUT as in to write-OUT
			def readable_mapping_bits(eightbits, direction, bt_message):
				#retval = f'{direction} {eightbits:08b}: '
				retval = f'{direction}: '
				maptype = ''
				if (eightbits & 0x80) >> 7:
					retval += 'NULLable '
					bt_message[direction+'_nullable'] = True
				else:
					bt_message[direction+'_nullable'] = False

				if (eightbits & 0x40) >> 6:
					retval += 'FunctionalMapping2 '
					bt_message[direction+'_mapping'] = True
				else:
					bt_message[direction+'_mapping'] = False
				if (eightbits & 0x20) >> 5:
					retval += 'whatisbitfive '

				if (eightbits & 0x10) >> 4:
					maptype += 'ABS '
				if (eightbits & 0x8) >> 3:
					maptype += 'REL '
				if (eightbits & 0x4) >> 2:
					maptype += 'DIS '

				if (eightbits & 0x2) >> 1:
					retval += 'whatisbittwo '
				if (eightbits & 0x1):
					retval += 'whatisbitone '

				bt_message[direction+'_maptype'] = maptype.strip()

				return retval
			bt_message['readable'] += readable_mapping_bits(payload[3], 'IN', bt_message)
			bt_message['readable'] += readable_mapping_bits(payload[4], 'OUT', bt_message)

		elif mode_info_type == 0x7:
			# Motor Bias, 8 bits, 0-100%
			bt_message['motor_bias'] = int.from_bytes(payload[3:4], byteorder="little", signed=False)
		elif mode_info_type == 0x8:
			# Capability bits 8[6]
			# FIXME: Well, good luck, the documents state something to the
			# effect of "your documentation is in another castle" in section 3.20.1
			bt_message['readable'] += ' Capabilities:'+' '.join(hex(n) for n in payload[3:9])

		elif mode_info_type == 0x80:
			# Value Format
			bt_message['datasets'] = payload[3]
			if payload[4] == 0x0:
				bt_message['dataset_type'] = '8bit'
			elif payload[4] == 0x1:
				bt_message['dataset_type'] = '16bit'
			elif payload[4] == 0x2:
				bt_message['dataset_type'] = '32bit'
			elif payload[4] == 0x3:
				bt_message['dataset_type'] = 'FLOAT'	# 32 bit IEEE 754
			else:
				bt_message['dataset_type'] = 'UNKNOWN'
			bt_message['total_figures'] = payload[5]
			bt_message['decimals'] = payload[6]
			bt_message['readable'] += " Datasets: "+str(bt_message['datasets'])+" Type: "+bt_message['dataset_type']+" Decimals: "+str(bt_message['decimals'])
		else:
			bt_message['readable'] += " ".join(hex(n) for n in payload[3:])

	def decode_port_value_single(bt_message):
		payload = bt_message['raw'][3:]
		bt_message['port'] = payload[0]
		bt_message['value'] = payload[1:]
		bt_message['readable'] += "port "+str(bt_message['port'] )+": "+" ".join(hex(n) for n in payload[1:])

	def decode_wdx_packet(message_bytes, source_char_uuid):

		bt_message = {
			'char_uuid': source_char_uuid,
			'error': False,
			'raw':message_bytes,
			'readable': ''
		}

		if len(bt_message['raw']) < 2:
			bt_message['error'] = True
			bt_message['readable'] += ": WDX Packet of insufficent length"
			return bt_message

		bt_message['wdx'] = {}
		packet_type = bt_message['raw'][0]
		if packet_type in Decoder.wdx_message_types:
			bt_message['wdx']['type'] = Decoder.wdx_message_types[packet_type]
			if packet_type != 3:
				bt_message['error'] = True
				bt_message['readable'] += ": WDX Packet decoder only fit to decode response packets"
				return bt_message
		else:
			bt_message['error'] = True
			bt_message['readable'] += f': Unknown WDX packet type {packet_type}'
			return bt_message

		register = bt_message['raw'][1]
		if register in Decoder.wdx_registers:
			bt_message['wdx']['register'] = Decoder.wdx_registers[register]
		else:
			bt_message['error'] = True
			bt_message['readable'] += f': Unknown WDX register {register} / {hex(register)}'
			return bt_message


		if register in Decoder.wdx_registers:
			bt_message['register'] = register

			if register == 0x20:
				bt_message['value'] = int.from_bytes(message_bytes[2:], byteorder="little", signed=False)
				bt_message['readable'] = f"Battery SoC: {bt_message['value']}"

			elif register == 0x21:
				bt_message['value'] = Decoder.string_and_strip_trailing_null(message_bytes[2:])
				bt_message['readable'] = f"Device Model: {bt_message['value']}"

			elif register == 0x22:
				bt_message['value'] = Decoder.string_and_strip_trailing_null(message_bytes[2:])
				bt_message['readable'] = f"Firmware: {bt_message['value']}"

			elif register == 0x80:
				bt_message['value'] = Decoder.string_and_strip_trailing_null(message_bytes[2:])
				bt_message['readable'] = f"Local Name: {bt_message['value']}"

			elif register == 0x81:
				bt_message['value'] = int.from_bytes(message_bytes[2:], byteorder="little", signed=False)
				bt_message['readable'] = f"Sound Volume: {bt_message['value']}"

			else:
				bt_message['value'] = bt_message['raw'][2:]
				bt_message['readable'] = f"{bt_message['wdx']['type']}:{bt_message['wdx']['register']} value {bt_message['value']}"

		else:
			bt_message['value'] = bt_message['raw'][2:]
			bt_message['readable'] = f"{bt_message['wdx']['type']}:{bt_message['wdx']['register']} value {bt_message['value']}"

		return bt_message

	def decode_wedo2_packet(message_bytes, source_char_uuid):

		bt_message = {
			'char_uuid': source_char_uuid,
			'error': False,
			'raw':message_bytes,
			'readable': ''
		}

		# FIXME: Where to put these constants?
		hub_attached_io_ = '00001527-1212-efde-1523-785feabcd123'
			# 0: Port Number on hub
			# 1: Hub Attached IO Event Type
			# 2: ?	WeDo "send" commands with a header size of 3
			#		(port aka "connectID", "commandID", payload_size). Maybe that's what's in here?
			#		Probably not, since it's not the port
			# 3: Port ID for device type
			# 4 - 11: ? Four 16-bit numbers? Two 32s?
			# Init (four devices: 'Current','Voltage','Piezo Tone','RGB Light')
			# 0x3 0x1 0x33 0x15 0x1 0x0 0x0 0x0 0x1 0x0 0x0 0x0 len:12
			# 0x4 0x1 0x34 0x14 0x1 0x0 0x0 0x0 0x1 0x0 0x0 0x0 len:12
			# 0x5 0x1 0x35 0x16 0x1 0x0 0x0 0x0 0x1 0x0 0x0 0x0 len:12
			# 0x6 0x1 0x36 0x17 0x1 0x0 0x0 0x0 0x1 0x0 0x0 0x0 len:12

			# Ports (Numbered 1 & 2)
			# 0x2 0x1 0x1 0x22 0x0 0x0 0x0 0x10 0x0 0x0 0x0 0x10 len:12
			# 0x1 0x1 0x0 0x26 0x0 0x0 0x0 0x10 0x0 0x0 0x0 0x10 len:12

			# (b'\x01\x00') Port 1, no device

		# FIXME: Name might be wrong
		port_mode_info = '00001561-1212-EFDE-1523-785FEABCD123'	# Value Format, "input format" in SDK


		# FIXME: Note that it auto-detaches the Matrix, but of course...
		# Set 'type' similar to LWP3 manually based on notification UUID received upon
		if bt_message['char_uuid'].lower() == hub_attached_io_.lower():
			bt_message['type'] = 0x4	# Hub Attached IO

			bt_message['port'] = message_bytes[0]
			bt_message['event'] = message_bytes[1]
			event_readable = Decoder.int8_dict_to_str(Decoder.io_event_type_str,bt_message['event'])
			# FIXME: needs a decoder for this readable
			bt_message['readable'] = "hub_attached_io"
			if bt_message['event'] == 0x0:
				bt_message['readable'] += f" {event_readable} on port {bt_message['port']}"
			elif bt_message['event'] == 0x1:
				if len(bt_message['raw']) == 12:
					bt_message['io_type_id'] = message_bytes[3]
					bt_message['readable'] += f" {event_readable} {Decoder.io_type_id_str[bt_message['io_type_id']]} on port {bt_message['port']}"
				else:
					bt_message['readable'] += f" {event_readable} UNKNOWN DATA"

		# RGB handily sends this on first start_notify() for the UUID
		elif bt_message['char_uuid'].lower() == port_mode_info.lower():
			bt_message['type'] = 0x44 # Signal PMI

			bt_message['readable'] = Decoder.int8_dict_to_str(Decoder.message_type_str, bt_message['type']) + " - "

			bt_message['pmi_revision'] = message_bytes[0]
			bt_message['port'] = message_bytes[1]	# ConnectID in SDK
			bt_message['io_type_id'] = message_bytes[2]
			bt_message['mode'] = message_bytes[3]
			bt_message['readable'] += f"{Decoder.io_type_id_str[bt_message['io_type_id']]} port {bt_message['port']} mode {bt_message['mode']}"
			bt_message['delta'] = int.from_bytes(message_bytes[4:8], byteorder="little", signed=False)
			if message_bytes[8] == 0x0:	# This byte is "unit" in the SDK
				bt_message['mode_info_type_readable'] = 'RAW'
			elif message_bytes[8] == 0x1:
				bt_message['mode_info_type_readable'] = 'PCT'
			elif message_bytes[8] == 0x2:
				bt_message['mode_info_type_readable'] = 'SI'
			else:
				bt_message['mode_info_type_readable'] = 'ERR_UNKNOWN_MODE_INFO_TYPE'

			bt_message['notifications_enabled_raw_value'] = message_bytes[9]	# FIXME: probably a bitfiled
			bt_message['data_size_in_bytes'] = message_bytes[10]	# Size of data to send/rec?

		return bt_message

	# --- Utilities

	def int8_dict_to_str(int8_dict,int8_value):
		if int8_value in int8_dict:
			return int8_dict[int8_value]
		else:
			return "__unknown("+str(hex(int8_value))+")"

	def uint16_bytes_to_int(uint16):
		# ok fine this is pointless
		return int.from_bytes(uint16, byteorder="little", signed=False)

	def version_bytes_to_str(int32):
		# 0x9 0x0 0x1 0x4 0x6 [ 0x0 0x0 0x0 0x2 ]    33554432
		# 0x9 0x0 0x1 0x3 0x6 [ 0x0 0x0 0x3 0x51 ] 1359151104
		verint = int.from_bytes(int32, byteorder="little", signed=True)
		major_mask = 0x70
		high_nibble_msb = int32[3] >> 4
		low_nibble_msb = int32[3] & 0xf
		major = high_nibble_msb & 0x7
		minor = low_nibble_msb

		bug_digit_1 = int(int32[2] >> 4)
		bug_digit_2 = int(int32[2] & 0xf)
		fix = (bug_digit_1*10)+bug_digit_2

		build_digit_1 = int(int32[1] >> 4)
		build_digit_2 = int(int32[1] & 0xf)
		build_digit_3 = int(int32[0] >> 4)
		build_digit_4 = int(int32[0] & 0xf)
		build = (build_digit_1*1000)+(build_digit_2*100)+(build_digit_3*10)+build_digit_4
		return "v"+str(major)+"."+str(minor)+"."+str(fix)+"."+str(build)

	def string_and_strip_trailing_null(str_bytearray):
		unicode_str = str_bytearray.decode()
		while unicode_str[-1] == '\u0000' and len(unicode_str) > 1:
			unicode_str = unicode_str[:-1]
		if unicode_str == '\u0000':
			return None
		else:
			return unicode_str

