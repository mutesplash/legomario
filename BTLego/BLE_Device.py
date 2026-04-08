import asyncio
import uuid
import logging
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .Decoder import Decoder

from .LPF_Devices import *

class BLE_Device():

	# If there was a level five... unfortunately, too complicated to bother implementing
	TRACE = False

	message_types = (
		'event',
		'info',
		'error',
		'device_ready',
		'connection_request',
		'property',
	)

	# ---- Initializations, obviously ----

	def __init__(self, advertisement_data=None, shortname=''):

		# Default to LWP
		self.characteristics = {
			'primary': '00001624-1212-efde-1623-785feabcd123'
		}
		self.packet_decoder = Decoder.decode_payload

		self.logger = logging.getLogger(__name__.split('.')[0])

		# Integer for LEGO part number, string for Bricklink (usually because part of a larger set)
		self.part_identifier = None

		self.advertisement = advertisement_data
		self.shortname = shortname
		self.client = None
		self.connected = False

		self.gatt_send_rate_limit = 0.1

		# keep around for... whatever?
		self.device = None
		self.address = None

		self.disconnect_callback = lambda bleak_dev: BLE_Device._bleak_disconnect(self, bleak_dev)
		# This is such a fun trick, we'll do it twice.
		# Give connected devices this function to let them send their own gatt messages
#		self.gatt_writer = lambda payload: BLE_Device._gatt_send(self, payload)
		self.gatt_writer = self._gatt_send

		self.message_queue = SimpleQueue()				# Messages to send to callbacks
		self.drainlock_changes_queue = SimpleQueue()	# Changes to those callbacks

		# Message type subscriptions reference count
		self.BLE_event_subscriptions = {}
		self._reset_event_subscription_counters()

		self.callbacks = {}
		# UUID indexed tuples of...
		# 0: callback function
		# 1: Tuple of message type subscriptions

		self.lock = asyncio.Lock()			# Connect lock
		self.drain_lock = asyncio.Lock()	# Draining message_queue

	# Override in subclass and call super if you subclass to initialize BLE_event_subscriptions with all available message types
	def _reset_event_subscription_counters(self):
		for message_type in BLE_Device.message_types:
			self.BLE_event_subscriptions[message_type] = 0;

	# ---- Things Normal People Can Do ----
	# (Not really all of them, there are some direct bluetooth things below)

	def dump_status(self):
		self.logger.info("CLIENT SERVICE LIST:")
		for svc in self.client.services:
			self.logger.info(f'\tService: {svc}')
			for handle_info in svc.characteristics:
				self.logger.info(f"\t\t Svc. Char.: {handle_info}")

		self.logger.info("EVENT SUBS\n"+json.dumps(dict(sorted(self.BLE_event_subscriptions.items())), indent=4))
		self.logger.info("DEVICE OBJECT REGISTERED CALLBACKS\n"+json.dumps(self.callbacks, indent=4, default=lambda function: '<function callback>'))
		if self.message_queue.qsize():
			self.logger.info(f'ALERT: {self.message_queue.qsize()} MESSAGE(S) AWAITING DEQUEUE')
		if self.drainlock_changes_queue.qsize():
			self.logger.info(f'ALERT: {self.drainlock_changes_queue.qsize()} MESSAGES NEEDING TO BE PROCESSED OFF DRAINLOCK')

	async def connect(self, device):
		async with self.lock:
			self.logger.info("Connecting to "+str(self.shortname)+"...")
			self.device = device
			try:
				self.client = BleakClient(device.address, self.disconnect_callback)
				await self.client.connect()
				if not self.client.is_connected:
					self.logger.error("Failed to connect after client creation")
					return
				try:
					paired = await self.client.pair()	# Not necessary: protection_level=1
					self.logger.info(f"Paired: {paired}")
				except NotImplementedError as e:
					# The UI necessary to connect should be a window that reads:
					#
					# Connection Request from: Mario XXXX_x_x
					# To connect to the device, click Connect to complete the connection process.
					#
					# To reject the connection with the device, click Cancel.
					# [ ] Ignore this device     [Cancel] [Connect]
					self.logger.info(f"MacOS pairing skipped, either already paired or hoping subsequent GATT writes will force UI to pop up...")

				self.logger.info("Connected to "+self.shortname+"! ("+str(device.name)+")")
				self.connected = True
				self.address = device.address
				await self.client.start_notify(self.characteristics['primary'], self._device_events)

				# turn back on everything everybody registered for (For reconnection)
				for event_sub_type,sub_count in self.BLE_event_subscriptions.items():
					if sub_count > 0:
						if not self._set_hardware_subscription(event_sub_type, True):
							self.logger.error("INVALID Subscription option on connect:"+event_sub_type)

			except Exception as e:
				self.logger.error("Unable to connect to "+str(device.address) + ": "+str(e))

		# Won't drain that info,player message without this
		await self._drain_messages()

	async def disconnect(self):
		async with self.lock:
			self.connected = False
			self.logger.info(self.shortname+" has disconnected.")

	def _bleak_disconnect(self, bleak_dev):
		"""Called by the BleakClient when disconnected"""
		self.logger.info(f'Bleak disconnect {self.shortname}: {bleak_dev.address}')
		# This whole function is a bit annoying as it isn't awaited by Bleak
		# and therefore can't be called async, so it can't lock to set this
		# variable.
		# The disconnect callback for BleakClient also can't be on an instance
		# of a class, because that needs to be passed self, and the callback
		# takes only one parameter: BleakClient
		# Therefore in init, there's a lambda that closes over self to pass it
		# here and calls this function on the class, allowing BleakClient to take
		# that lambda as the callback, which means it's a bit deceptive to use
		# self as the variable name, but everything is dying here so... WHATEVER
		self.connected = False
		# Note about why self has to be passed, anyway
		# https://stackoverflow.com/a/10003918

		# Adding anything to the message_queue won't get kicked until the device is reconnected
		thisloop = asyncio.get_running_loop()
		if thisloop:
			if thisloop.is_running():
				pass
				# Putting anything on thisloop doesn't work.  The event doesn't get drained until the device is reconnected because it's driven by Bleak's callback

	async def is_connected(self):
		async with self.lock:
			return self.connected

	# set/unset registrations separately
	async def register_callback(self, callback):
		callback_uuid = str(uuid.uuid4())
		self.drainlock_changes_queue.put(('callback', 'register', (callback_uuid,callback)))

		# If outside of the drain, process now!
		if not self.drain_lock.locked():
			async with self.drain_lock:
				await self.__process_drainlock_queue()

		return callback_uuid

	async def unregister_callback(self, callback_uuid):
		self.drainlock_changes_queue.put(('callback', 'unregister', (callback_uuid,)))

		# If outside of the drain, process now!
		if not self.drain_lock.locked():
			async with self.drain_lock:
				await self.__process_drainlock_queue()

	# Hmm... just because this returns true doesn't mean you're going to get the messages (see failure modes in __process_drainlock_queue)
	async def subscribe_to_messages_on_callback(self, callback_uuid, message_type, subscribe=True):
		# Not going to check if the callback is valid here, because it could be on the queue

		# Contains all message_types for the class after _reset_event_subscription_counters() in subclasses
		# FIXME: Not strictly true.  This is ALL of the subscriptions that are possible.
		if not message_type in self.BLE_event_subscriptions:
			self.logger.error(f'Class {self.__class__.__name__} can\'t subscribe to {message_type}')
			return False

		self.drainlock_changes_queue.put(('subscription', 'change', (callback_uuid,message_type,subscribe)))

		# If outside of the drain, process now!
		if not self.drain_lock.locked():
			async with self.drain_lock:
				await self.__process_drainlock_queue()

		return True

	# ---- Message processing ----

	# MUST be called within drain_lock because commands in here modify callbacks
	# and their subscriptions and therefore the drain loop processing.
	# Callback register, unregister, and message subscribe have to be processed
	# AFTER the message queue is drained, but WITHIN the (drain)lock on the queue
	# since dispatching anything in the queue will be affected
	async def __process_drainlock_queue(self):

		while not self.drainlock_changes_queue.empty():
			change_order = self.drainlock_changes_queue.get()
			parameters = change_order[2]
			if change_order[0] == 'callback':
				if change_order[1] == 'unregister':
					callback_uuid = parameters[0]
					self.logger.debug(f'Unregistering callback {callback_uuid}')

					if not callback_uuid in self.callbacks:
						self.logger.error(f'Given UUID {callback_uuid} doesn\'t exist to unregister')
						continue

					callback_settings = self.callbacks[callback_uuid]
					current_subscriptions = callback_settings[1]

					self.logger.debug(f'Unusbscribe processing {callback_uuid}')
					for subscription in current_subscriptions:
						self._set_callback_subscriptions(parameters[0], subscription, False)

						if (self.BLE_event_subscriptions[subscription] <= 0):
							if not self._set_hardware_subscription(subscription, False):
								self.logger.error(f'UUID {callback_uuid} requested unsubscribe... but.. the device was not connected?')
					self.logger.debug(f'Finished processing unsubscribes {callback_uuid}')

					self.callbacks.pop(callback_uuid, None)

				# FIXME: Doesn't actually take the third parameter
				# (callback_uuid,callback,subscription_tuple)
				elif change_order[1] == 'register':
					self.logger.debug(f'Registering callback {parameters[0]}')
					self.callbacks[parameters[0]] = (parameters[1], ())

			# Caller verifies message_type
			# (callback_uuid, message_type, boolean_subscription)
			elif change_order[0] == 'subscription' and change_order[1] == 'change':
				self.logger.debug(f'Requesting {parameters[2]} subscription to {parameters[1]} on callback {parameters[0]}')

				# first subscribing callback: turn on the event	OR last subscribing callback: turn off the subscription
				# Otherwise, don't bother the hardware
				if (self.BLE_event_subscriptions[parameters[1]] <= 0 and parameters[2]) or (self.BLE_event_subscriptions[parameters[1]] == 1 and not parameters[2]):
					self._set_callback_subscriptions(parameters[0], parameters[1], parameters[2])
					if not self._set_hardware_subscription(parameters[1], parameters[2]):
						self.logger.error("INVALID Subscription option:"+parameters[1])
				else:
					self._set_callback_subscriptions(parameters[0], parameters[1], parameters[2])

		if self.TRACE:
			self.logger.debug(f'DONE WITH DRAINLOCK QUEUE')

	async def _drain_messages(self):
		async with self.drain_lock:
			while not self.message_queue.empty():
				message = self.message_queue.get()
				served = False
				for callback_uuid, callback_settings in self.callbacks.items():
					# message_type in subscriptions
					if message[0] in callback_settings[1]:
						# callback( ( dev_addr, type, key, value ) )
						if self.TRACE:
							self.logger.debug(f'DRAINING {message} to {callback_uuid}')
						await callback_settings[0]((callback_uuid,) + message)
						served = True
				if not served:
					self.logger.debug(f'{self.shortname} had no subscribers for message:{message}')

			# Process any registrations that occurred during the above dispatch

			if self.TRACE:
				self.logger.debug(f'PROCESS DRAINLOCK QUEUE')
			await self.__process_drainlock_queue()
			if self.TRACE:
				self.logger.debug(f'PROCESS DRAINLOCK COMPLETE')

	# return the tuple of subscriptions that were set
	# Assumes you filtered this to only valid message types
	def _set_callback_subscriptions(self, callback_uuid, message_type, subscribe=True):
		if not callback_uuid in self.callbacks:
			# Could happen with getting deferred in the queue?
			self.logger.error(f'Given UUID {callback_uuid} disappeared.  Failed to subscribe to {message_type}')
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
			self.logger.debug(f'Callback subscriptions unchanged after requesting {message_type} to {subscribe}')
		else:
			if subscribe:
				self.BLE_event_subscriptions[message_type] += 1
				self.logger.debug(f'Setting callback {callback_uuid} subscription to {message_type}')
			else:
				self.BLE_event_subscriptions[message_type] -= 1
				self.logger.debug(f'Removing callback {callback_uuid} subscription to {message_type}')

			self.callbacks[callback_uuid] = (callback_settings[0], new_subscriptions)

		return new_subscriptions

	# Checks all Properties and Ports for LPF devices that handle the given message_type
	# Subscribes or unsubscribes to these messages as requested
	def _set_hardware_subscription(self, message_type, should_subscribe=True):
		# Base class doesn't do anything with this
		pass

	# Bleak events get sent here
	async def _device_events(self, sender, data):
		# Suddenly _which_ characteristic you subscribe to becomes super important when WeDo2 is involved...
		bt_message = self.packet_decoder(data, sender.uuid)
		msg_prefix = self.shortname+" "
		if bt_message['error']:
			self.logger.error(msg_prefix+"ERR:"+bt_message['readable'])
			self.message_queue.put(('error','message',bt_message['readable']))

		else:
			if not await self._process_bt_message(bt_message):
				# debug for messages we've never seen before
				self.logger.info(msg_prefix+"-?- "+bt_message['readable'],1)

		self.logger.debug(f'{self.shortname} Draining for: '+bt_message['readable'])
		await self._drain_messages()
		if self.TRACE:
			self.logger.debug(f'{self.shortname} Drained')

	# Returns false if unprocessed
	# Override in subclass, call super if you don't process the bluetooth message type
	async def _process_bt_message(self, bt_message):
		return True

	# Override if you wanna decode a property to send _additional_ messages
	def _decode_property(self, prop_id, value):
		pass

	# ---- Make data useful for the processing ----

	# ---- Bluetooth port writes for mortals ----

	def _gatt_send(self, payload, target):
		from . import await_function_off_bleak_callback

		target_char_uuid = None
		if target in self.characteristics:
			if self.TRACE:
				self.logger.debug(f"GATT SELECT SEND: {uuid}")
			target_char_uuid = target_char_uuid = self.characteristics[target]

		if not target_char_uuid:
			target_char_uuid = self.characteristics['primary']

		if self.connected:
			if self.TRACE:
				self.logger.debug("GATT SEND: "+" ".join(hex(n) for n in payload))
			await_function_off_bleak_callback(self.client.write_gatt_char(target_char_uuid, payload))
			if self.TRACE:
				self.logger.debug("GATT CMPL: "+" ".join(hex(n) for n in payload))
			return True
		else:
			self.logger.warn("GATT SEND PROHIBITED: NOT CONNECTED")
			return False

	# ---- Bluetooth port writes for the class ----
