from binascii import hexlify

# FIXME: Completely confused on upstream/downstream, fix the nomenclature in the comments

class BTLego():

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
		0x22:'External Tilt Sensor',
		0x23:'Motion Sensor',
		0x25:'Vision Sensor',
		0x26:'External Motor with Tacho',
		0x27:'Internal Motor with Tacho',
		0x28:'Internal Tilt',

		# My names
		0x46:'Mario Events',
		0x47:'Mario Tilt Sensor',
		0x49:'Mario RGB Scanner',
		0x4A:'Mario Pants Sensor',
		0x55:'Mario Alt Events',
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
		0x6:'Battery Voltage',
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
		0x12:'Mario Volume'		# Can't enable updates on this property, which is annoying. Also won't send an update when you update it
	}

	subscribable_hub_properties = [
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

	def __init__(self):
		# reverse map some dicts so you can index them either way
		self.message_type_ints = dict(map(reversed, self.message_type_str.items()))
		self.hub_property_ints = dict(map(reversed, self.hub_property_str.items()))
		pass

	def decode_payload(message_bytes):
		bt_message = {
			'error': False,
			'raw':message_bytes
		}
		length = message_bytes[0]
		unused_hub_id = message_bytes[1]
		if len(message_bytes) != length:
			bt_message['error'] = True
			bt_message['readable'] = "CORRUPTED MESSAGE: stated len "+length+" != "+str(len(message_bytes))+" ".join(hex(n) for n in message_bytes)
			return bt_message
		bt_message['type']  = message_bytes[2]
		bt_message['readable'] = BTLego.int8_dict_to_str(BTLego.message_type_str, bt_message['type']) + " "

		if bt_message['type'] == 0x1:
			BTLego.decode_hub_properties(bt_message)
		elif bt_message['type'] == 0x2:
			BTLego.decode_hub_action(bt_message)
		elif bt_message['type'] == 0x3:
			BTLego.decode_hub_alert(bt_message)
		elif bt_message['type'] == 0x4:
			BTLego.decode_hub_attached_io(bt_message)

		# Undocumented mario messages
		#elif bt_message['type'] == 0x7:
		#elif bt_message['type'] == 0xb:

		elif bt_message['type'] == 0x44:
			BTLego.decode_port_mode_info_request(bt_message)
		elif bt_message['type'] == 0x45:
			BTLego.decode_port_value_single(bt_message)
		elif bt_message['type'] == 0x47:
			BTLego.decode_port_input_format_single(bt_message)
		elif bt_message['type'] == 0x82:
			BTLego.decode_port_output_command_feedback(bt_message)
		else:
			bt_message['error'] = True
			bt_message['readable'] += "No decoder for message: "+" ".join(hex(n) for n in message_bytes)

		return bt_message

	def decode_hub_action(bt_message):
		if len(bt_message['raw']) != 4:
			bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(len(bt_message['raw']))+" is wrong for a hub action: "+" ".join(hex(n) for n in payload)
			bt_message['error'] = True
			return

		bt_message['action'] = bt_message['raw'][3]
		bt_message['action_str'] = BTLego.int8_dict_to_str(BTLego.hub_action_type, bt_message['action'])

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
		property_involved_str = BTLego.int8_dict_to_str(BTLego.hub_property_str, property_involved)

		bt_message['operation'] = payload[1]
		property_operation_str = BTLego.int8_dict_to_str(BTLego.hub_property_op_str, payload[1])

		# 0x9 0x0 0x1 0x3 0x6 [ 0x0 0x0 0x3 0x51 ]
		# FIXME: Incomplete
			#0xb:'System Type ID',
			#0xc:'H/W Network ID',
			#0xe:'Secondary MAC Address',
			#0xf:'Hardware Network Family'

		property_value = "IDK_WAT"
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
			property_value = BTLego.version_bytes_to_str(payload[2:])
			bt_message['value'] = property_value

		# 'HW Version'
		elif property_involved == 0x4:
			if length != 9:
				bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a uint32 hub property: "+" ".join(hex(n) for n in payload)
				bt_message['error'] = True
				return
			property_value = BTLego.version_bytes_to_str(payload[2:])
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
			bt_message['value'] = BTLego.uint16_bytes_to_int(payload[2:])
			property_value = str(bt_message['value'])

		# 'Primary MAC Address'
		elif property_involved == 0xd:
			# 5 + 6
			if length != 11:
				bt_message['readable'] += "CORRUPTED MESSAGE: payload len "+str(length)+" is wrong for a uint[15] property: "+" ".join(hex(n) for n in payload)
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
		status = "Status OK"
		bt_message['status'] = False
		if payload[2] == 0xff:
			status = "ALERT!"
			bt_message['status'] = True
			bt_message['alert_type_str'] = BTLego.int8_dict_to_str(BTLego.hub_alert_type_str, payload[0])
			bt_message['operation_str'] = BTLego.int8_dict_to_str(BTLego.hub_alert_op_str, payload[1])

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
		event = BTLego.int8_dict_to_str(BTLego.io_event_type_str,payload[1])
		bt_message['event'] = payload[1]
		# --- --- --- 0x0 0x1 [0x47 0x0 0x0 0x0 0x3 0x51 0x1 0x0 0x0 0x0 ]
		# attached
		if io_size_indicator == 15:
			bt_message['io_type_id'] = BTLego.uint16_bytes_to_int(payload[2:4])
			hw_rev = BTLego.version_bytes_to_str(payload[4:8])
			bt_message['hw_ver_str'] = hw_rev
			sw_rev = BTLego.version_bytes_to_str(payload[8:12])
			bt_message['sw_ver_str'] = sw_rev
			bt_message['readable'] += "port "+str(port)+" "+event+" IOTypeID:"+str(bt_message['io_type_id'])+" hw:"+hw_rev+" sw:"+sw_rev
		# attached_virtual
		elif io_size_indicator == 9:
			iotype = 'virtual_attached'
			bt_message['io_type_id'] = BTLego.uint16_bytes_to_int(payload[2:4])
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

		bt_message['readable'] += "port "+str(port)+" mode " + str(mode) + " infotype: " + BTLego.int8_dict_to_str(BTLego.mode_info_type_str,mode_info_type) + " "
		if mode_info_type == 0x0 or mode_info_type == 0x4:
			# NAME or SYMBOL
			bt_message['readable'] += bytearray(payload[3:]).decode()
		else:
			bt_message['readable'] += " ".join(hex(n) for n in payload[3:])

	def decode_port_value_single(bt_message):
		payload = bt_message['raw'][3:]
		bt_message['port'] = payload[0]
		bt_message['value'] = payload[1:]
		bt_message['readable'] += "port "+str(bt_message['port'] )+": "+" ".join(hex(n) for n in payload[1:])

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
