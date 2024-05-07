import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class PUH_IMU_Gesture(LPF_Device):

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x36
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		# Doesn't support streaming with zero
		self.delta_interval = 1

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'GEST', ('gesture',)],
		}

	# Decode Port Value - Single
	# Return (type, key, value)
	def decode_pvs(self, port, data):
		if port != self.port:
			print('Bad port')
			return None

		if len(data) != 1:
			print('UNKNOWN GESTURE DATA '+' '.join(hex(n) for n in data))
			return None

		gesture = int.from_bytes(data, byteorder="little", signed=True)

		if gesture == 0:
			gesture = 'none'
		elif gesture == 1:
			gesture = 'knock'
		elif gesture == 2:
			# Kind of violent, you don't want this
			gesture = 'crashed'
		elif gesture == 3:
			gesture = 'shake'
		elif gesture == 4:
			gesture = 'falling'
		else:
			# Port info says this should never happen
			gesture = f'Number_{gesture}'

		return ('hub2','gesture', gesture)
