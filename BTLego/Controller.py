import asyncio
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder

class Controller(BLE_Device):
	# 0:	Don't debug
	# 1:	Print weird stuff
	# 2:	Print most of the information flow
	# 3:	Print stuff even you the debugger probably don't need
	DEBUG = 0

	message_types = (
		'event',
		'info',
		'error',
		'controller_buttons',
		'controller_rgb',
		'controller_volts',
		'controller_RSSI',
		'connection_request'
	)

	RGB_LIGHT_PORT = 52
	CONTROLLER_VOLTS_PORT = 59
	BUTTONS_LEFT_PORT = 0
	BUTTONS_RIGHT_PORT = 1
	CONTROLLER_RSSI_PORT = 60

	# override
	async def set_event_subscriptions(self, current_subscriptions):
		# FIXME: Uhh, actually doesn't allow you to unsubscribe.  Good design here. Top notch
		if self.connected:
			for subscription in current_subscriptions:
				if subscription == 'event':
					await self.set_updates_for_hub_properties([
						['Button',True]				# Works as advertised (the "button" is the bluetooth button)
					])

				elif subscription == 'controller_buttons':
					await self.set_port_subscriptions([
						[self.BUTTONS_LEFT_PORT,1,0,True],
						[self.BUTTONS_RIGHT_PORT,1,0,True]
					])
					# 0: Only reports center buttons
					# 1, 2: Buggy "either press - or +" one time per side (can be opposites!)
					# 3: returns 0x0 and nothing else
					# 4: returns 0x0 0x0 0x0 and nothing else

				elif subscription == 'controller_rgb':
					await self.set_port_subscriptions([[self.RGB_LIGHT_PORT,0,5,True]])
				elif subscription == 'controller_volts':
					await self.set_port_subscriptions([[self.CONTROLLER_VOLTS_PORT,0,5,True]])
				elif subscription == 'controller_RSSI':
					await self.set_port_subscriptions([[self.CONTROLLER_RSSI_PORT,0,5,True]])

				elif subscription == 'info':
					await self.set_updates_for_hub_properties([
						['Advertising Name',True]	# I guess this works different than requesting the update because something else could change it, but then THAT would cause an update message

						# Kind of a problem to implement in the future because you don't want these spewing at you
						# Probably need to be separate types
						#['RSSI',True],				# Doesn't really update for whatever reason
						#['Battery Voltage',True],	# Transmits updates pretty frequently
					])
#				elif subscription == 'error'
# You're gonna get these.  Don't know why I even let you choose?
				else:
					Controller.dp("INVALID Subscription option:"+subscription)

		else:
			Controller.dp("NOT CONNECTED.  Not setting port subscriptions",2)

	# override
	async def device_events(self, sender, data):
		# Bleak events get sent here
		bt_message = Decoder.decode_payload(data)
		msg_prefix = self.system_type+" "

		if bt_message['error']:
			Controller.dp(msg_prefix+"ERR:"+bt_message['readable'])
			self.message_queue.put(('error','message',bt_message['readable']))

		else:
			if Decoder.message_type_str[bt_message['type']] == 'port_input_format_single':
				if Controller.DEBUG >= 2:
					msg = "Disabled notifications on "
					if bt_message['notifications']:
						# Returned typically after gatt write
						msg = "Enabled notifications on "

					port_text = "port "+str(bt_message['port'])
					if bt_message['port'] in self.port_data:
						# Sometimes the hub_attached_io messages don't come in before the port subscriptions do
						port_text = self.port_data[bt_message['port']]['name']+" port ("+str(bt_message['port'])+")"

					Controller.dp(msg_prefix+msg+port_text+", mode "+str(bt_message['mode']), 2)

			# Sent on connect, without request
			elif Decoder.message_type_str[bt_message['type']] == 'hub_attached_io':
				event = Decoder.io_event_type_str[bt_message['event']]
				if event == 'attached':
					dev = "UNKNOWN DEVICE"
					if bt_message['io_type_id'] in Decoder.io_type_id_str:
						dev = Decoder.io_type_id_str[bt_message['io_type_id']]
					else:
						dev += "_"+str(bt_message['io_type_id'])

					if bt_message['port'] in self.port_data:
						Controller.dp(msg_prefix+"Re-attached "+dev+" on port "+str(bt_message['port']),2)
						self.port_data[bt_message['port']]['status'] = bt_message['event']
					else:
						Controller.dp(msg_prefix+"Attached "+dev+" on port "+str(bt_message['port']),2)
						self._init_port_data(bt_message['port'], bt_message['io_type_id'])

				elif event == 'detached':
					Controller.dp(msg_prefix+"Detached "+dev+" on port "+str(bt_message['port']),2)
					self.port_data[bt_message['port']]['status'] = 0x0 # io_event_type_str

				else:
					Controller.dp(msg_prefix+"HubAttachedIO: "+bt_message['readable'],1)

			elif Decoder.message_type_str[bt_message['type']] == 'port_value_single':
				if not bt_message['port'] in self.port_data:
					Controller.dp(msg_prefix+"WARN: Received data for unconfigured port "+str(bt_message['port'])+':'+bt_message['readable'])
				else:
					pd = self.port_data[bt_message['port']]
					if pd['name'] == 'Powered Up Handset Buttons':
						self.decode_button_data(bt_message['port'], bt_message['value'])
					elif pd['name'] == 'Powered Up hub Bluetooth RSSI':
						self.decode_bt_rssi_data(bt_message['value'])
					elif pd['name'] == 'Voltage':
						self.decode_voltage_data(bt_message['value'])
					else:
						if Controller.DEBUG >= 2:
							Controller.dp(msg_prefix+"Data on "+self.port_data[bt_message['port']]['name']+" port"+":"+" ".join(hex(n) for n in data),2)

			elif Decoder.message_type_str[bt_message['type']] == 'hub_properties':
				if not Decoder.hub_property_op_str[bt_message['operation']] == 'Update':
					# everything else is a write, so you shouldn't be getting these messages!
					Controller.dp(msg_prefix+"ERR NOT UPDATE: "+bt_message['readable'])

				else:
					if not bt_message['property'] in Decoder.hub_property_str:
						Controller.dp(msg_prefix+"Unknown property "+bt_message['readable'])
					else:
						if Decoder.hub_property_str[bt_message['property']] == 'Button':
							if bt_message['value']:
								Controller.dp(msg_prefix+"Bluetooth button pressed!",2)
								self.message_queue.put(('event','button','pressed'))
							else:
								# Well, nobody cares if it WASN'T pressed...
								pass

						# The app seems to be able to subscribe to Battery Voltage and get it sent constantly
						elif Decoder.hub_property_str[bt_message['property']] == 'Battery Voltage':
							Controller.dp(msg_prefix+"Battery is at "+str(bt_message['value'])+"%",2)
							self.message_queue.put(('info','batt',bt_message['value']))

						elif Decoder.hub_property_str[bt_message['property']] == 'Advertising Name':
							Controller.dp(msg_prefix+"Advertising as \""+str(bt_message['value'])+"\"",2)
							pass

						else:
							Controller.dp(msg_prefix+bt_message['readable'],2)

			elif Decoder.message_type_str[bt_message['type']] == 'port_output_command_feedback':
				# Don't really care about these messages?  Just a bunch of queue status reporting
				Controller.dp(msg_prefix+" "+bt_message['readable'],3)
				pass

			elif Decoder.message_type_str[bt_message['type']] == 'hub_alerts':
				# Ignore "status OK" messages
				if bt_message['status'] == True:
					Controller.dp(msg_prefix+"ALERT! "+bt_message['alert_type_str']+" - "+bt_message['operation_str'])
					self.message_queue.put(('error','message',bt_message['alert_type_str']+" - "+bt_message['operation_str']))

			elif Decoder.message_type_str[bt_message['type']] == 'hub_actions':
				self.decode_hub_action(bt_message)

			elif Decoder.message_type_str[bt_message['type']] == 'port_info':
				await self.decode_mode_info_and_interrogate(bt_message)

			elif Decoder.message_type_str[bt_message['type']] == 'port_mode_info':
				# Debug stuff for the ports and modes, similar to list command on BuildHAT
				self.decode_port_mode_info(bt_message)

			elif Decoder.message_type_str[bt_message['type']] == 'hw_network_cmd':
				self.decode_hardware_network_command(bt_message)

			else:
				# debug for messages we've never seen before
				Controller.dp(msg_prefix+"-?- "+bt_message['readable'],1)

		Controller.dp("Draining for: "+bt_message['readable'],3)
		await self.drain_messages()

	# ---- Make data useful ----

	# After getting the Value Format out of the controller, that allowed me to find this page
	# https://virantha.github.io/bricknil/lego_api/lego.html#remote-buttons
	def decode_button_data(self, port, data):
		if len(data) != 1:
			Controller.dp(self.system_type+" UNKNOWN BUTTON DATA, WEIRD LENGTH OF "+str(len(data))+":"+" ".join(hex(n) for n in data))
			# PORT 1: handset UNKNOWN BUTTON DATA, WEIRD LENGTH OF 3:0x0 0x0 0x0
			return

		side = 'left'		# A side
		if port == 1:
			side = 'right'	# B side

		button_id = data[0]
		if button_id == 0x0:
			self.message_queue.put(('controller_buttons',side,'zero'))
		elif button_id == 0x1:
			self.message_queue.put(('controller_buttons',side,'plus'))
		elif button_id == 0x7f:
			self.message_queue.put(('controller_buttons',side,'center'))
		elif button_id == 0xff:
			self.message_queue.put(('controller_buttons',side,'minus'))

		else:
			Controller.dp(self.system_type+" Unknown button "+hex(button_id))

	def decode_bt_rssi_data(self, data):
		# Lower numbers are larger distances from the computer
		rssi8 = int.from_bytes(data, byteorder="little", signed=True)
		Controller.dp("RSSI: "+str(rssi8))

	def decode_voltage_data(self,data):
		# FIXME: L or S and what do they mean?
		volts16 = int.from_bytes(data, byteorder="little", signed=False)
		Controller.dp("Voltage: "+str(volts16)+ " millivolts")

	# ---- Random stuff ----

	def dp(pstr, level=1):
		if Controller.DEBUG:
			if Controller.DEBUG >= level:
				print(pstr)

	# ---- Bluetooth port writes ----

	async def write_mode_data_RGB_color(self, port, color):
		if color not in Decoder.rgb_light_colors:
			return

		payload = bytearray([
			0x7,	# len
			0x0,	# padding
			0x81,	# Command: port_output_command
			# end header
			port,
			0x0,	# Startup and completion information (Buffer if necessary (upper 0x0), No Action (lower 0x0))
			0x51,	# Subcommand: WriteDirectModeData
			0x0,	# Mode (Could be 1 according to LEGO BTLE docs?)
			color
		])
		payload[0] = len(payload)
		# Controller.dp(self.system_type+" Debug RGB Write"+" ".join(hex(n) for n in payload))
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, payload)
		await asyncio.sleep(0.1)
