import asyncio
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder

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
class Mario(BLE_Device):
	# 0:	Don't debug
	# 1:	Print weird stuff
	# 2:	Print most of the information flow
	# 3:	Print stuff even you the debugger probably don't need
	# 4:	Debug the code table generation too (mostly useless)
	DEBUG = 0

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

	message_types = (
		'event',
		'motion',
		'gesture',
		'scanner',
		'pants',
	)

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
			# More different events?  Might be bluetooth events.
	VOLTS_PORT = 6		# Constant stream of confusing data
		# Mode 0: VLT L
		# Mode 1: VLT S

	code_data = None
	gr_codespace = {}
	br_codespace = {}
	tr_codespace = {}
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

	# I don't know why pants codes are transmitted over the events port,
	# or why they are different numbers, but here we are
	event_pants_codes = {
		0x0:'no',
		0x1:'mario',
		0x2:'propeller',
		0x3:'cat',
		0x4:'fire',
		0x5:'builder',
		0x6:'penguin',
		0x7:'tanooki',
		0x8:'luigi',
		0x9:'bee',
		0xa:'frog',
		0xb:'vacuum',	# Triggers on EITHER pin.  Both pins down trigger the vacuum
		0xc:'invalid',	# Not just any invalid pin combo, ALL of them
		0xd:'dress',
		0xe:'cat',		# Peach's cat
		0xf:'ice'
	}

	# FIXME: Incomplete and don't rely on this not changing
	event_scanner_coinsource = {
		6:'GOAL',
		9:'free',			# Just hopping around
#		8:'fixme unknown after wakeup',
#		13:'fixme unknown after eating cookies',
#		12:'fixme unknown',
#		14:'fixme: eating cake?',
		33:'BDARR 2',
		34:'SPIN 1',
		36:'SPIN 2',
		37:'WAGGLE',		# 1, 2, 3, 4
		39:'SPIN 3',
		40:'SPIN 4',
		42:'BDARR 5',
		43:'NES',
		44:'BDARR 1',
		45:'red coins',		# 10 if complete
		46:'RAFT',
		48:'GEAR',
		49:'NUT',
		50:'SEESAW',
		51:'SKEWER',
		52:'BROOM',
		53:'SPIN 5',
		54:'BIASDIR',
		55:'FERRIS',
		56:'STEERING',
		59:'CLOWN',
		60:'DIVING',
		62:'SHOE',
		63:'PCTHRONE',
		65:'BALLOON',
		66:'GOOMBA or LAVA',		# 1
		68:'SPINY or BUZZY',			# 1
		67:'BOB-OMB or BOMB 2 or BOMB 3 or PARABOMB',
		69:'BLOOPER',
		70:'GHOST or BOO',			# Need to use a star
		71:'GLDGHOST',		# star
		72:'GRBG GHO',		# star
		73:'GRBGHOST',		# star
		74:'BOGMIRE',
		75:'SWING',			# varies
		80:'SHY GUY',		# 1
		81:'WHOMP',
		82:'DRY BONE',
		83:'BOWSER 2',		# ? seems inconsistent, or maybe coin count outside of the course is
		84:'KOOPA 1 or KOOPA 2',
		85:'THWOMP',
		87:'YOSHI',			# 5, 2 when scanned again
		86:'TOAD',			# 5
		88:'POKEY',			# 1
		89:'EXPLODE',		# 1
		90:'KING BOO',		# star
		91:'JrBOWSER',
		92:'TOADETTE',		# 5
		93:'IGGY or BRVYT or LARRY or LUDWIG or LEMMY',			# 10
		94:'THWIMP',
		96:'BRAMBALL',
		97:'KPARAT 1 or KPARAT 2',
		98:'CHOMP',
		58:'DORRIE',		# 5
		99:'YOSHIEGG',
		100:'BOOMBOOM',
		101:'SUMO',
		102:'REZNOR 2',		# Another backwards numbering...
		103:'REZNOR 1',
		104:'LAKITU',
		105:'ROCKY',
		106:'AMP',
		107:'KAMEK',
		109:'SHIPHEAD',
		110:'CLAW',
		111:'MAST',
		112:'GRRROL',
		113:'TOAD 2',
		114:'FREEZIE',
		115:'YOSHI E2',
		116:'BULLY',
		117:'EGADD',		# 3 if again
		118:'KINGBOO2',		# star
		119:'POLTER',
		121:'YOSHI E3',
		124:'BPENGUIN',
		128:'? BLOCK',
		132:'P-Switch jumping',	# 1, 3, 5, all sorts....
		134:'COIN 1, 2 or 3',	# 10
		135:'PIRANHA',
		136:'STONE',
		137:'vacuum yellow gem',
		138:'jumping on a course',
		139:'139?',			# jumping around with the star???
		129:'1,2,3 Blocks',	# 3 each and then 10 if completed
		141:'vacuum brown gem',
		141:'vacuum red gem',
		142:'vacuum purple gem',
		143:'vacuum pink gem',	# looks kind of red
		147:'COINCOFF',		# 1
		146:'blue, purple, or green gem',	# multiple codes
		148:'BIG URCH',
		149:'eating any of the FRUITs',		# 10
		150:'PRESENT',
		151:'PRESENT 2',
		152:'PRESENT 3',
		153:'skating on ice',
		155:'eating the CAKE',		# 5 if already riding
		156:'BOMBWARP',		# 8????
		157:'BABYOSHI',		# 5
		158:'BIGSPIKE',
		159:'BOOMRBRO',		# 5
		160:'HAMMRBRO',
		163:'BIGKOOPA',
		164:'YOSHI E4',
		165:'BIG GOOM',
		166:'BIRDO throw',		# Throw Birdo's egg back at them
		167:'SMOLSUMO',		# 5
		168:'CONKDOR',		# 2
		169:'FLIPRUS',		# 2
		170:'DONKEY Kong',
		173:'CHKPOINT',
		174:'LAVALIFT',		# varies
		175:'YOSHI E5',
		176:'fireball pants blip',
		179:'propeller pants flying',
		181:'tanooki pants twirl',
		182:'bee pants flying',
		184:'vacuumed anything (also ghost?)',
		187:'NABBIT',
		188:'TURNIP throw',
		189:'eating BANANA',
		190:'BONGOS session',
		191:'fishing reward',
		192:'eating PICNIC cookies',
		193:'feeding RAMBI',
		194:'SNAGGLES',
		195:'EXERCISE',
		196:'PLANE',
		197:'CRANKY Kong',
		200:'MORTON',
		201:'FUNKY Kong',
		202:'CHEST',
		203:'BALLOON',
		205:'MUSIC',
		255:'gold grow turns item into coins' # 5 (turnip, mushroom, 1-up, goldbone)
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

	def __init__(self,advertisement_data=None, json_code_dict=None):
		super().__init__(advertisement_data)

		# Translates static event sequences into messages
		self.event_data_dispatch = {
		}

		self.volume = 100

		if not Mario.code_data:
			Mario.code_data = json_code_dict

		# reverse map some dicts so you can index them either way
		if not Mario.app_icon_ints:
			Mario.app_icon_ints = dict(map(reversed, self.app_icon_names.items()))
		if not Mario.app_icon_color_ints:
			Mario.app_icon_color_ints = dict(map(reversed, self.app_icon_color_names.items()))

		self.__init_data_dispatch()

	def __init_data_dispatch(self):

		# ( key, type, value)
		# NOTE: The line data is in type, key, value order, but they are reasonably grouped around keys

		# 0x0
		self.event_data_dispatch[(0x0,0x0,0x0)] = lambda dispatch_key: {
			# When powered on and BT connected (reconnects do not seem to generate)
			Mario.dp(self.system_type+" events ready!",2)
		}

		# 0x18: General statuses?
		self.event_data_dispatch[(0x18,0x1,0x0)] = lambda dispatch_key: {
			# Course reset
			# Happens a little while after the flag, sometimes on bootup too
			self.message_queue.put(('event','course','reset'))
		}
		self.event_data_dispatch[(0x18,0x1,0x1)] = lambda dispatch_key: {
			# turns "ride", "music", and "vacuum" off before starting
			self.message_queue.put(('event','course','start'))
		}
		self.event_data_dispatch[(0x18,0x2,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','consciousness','asleep'))
		}
		self.event_data_dispatch[(0x18,0x2,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','consciousness','awake'))
		}
		self.event_data_dispatch[(0x18,0x3,0x0)] = lambda dispatch_key: {
			Mario.dp(self.system_type+" course status REALLY FINISHED",2) # Screen goes back to normal, sometimes 0x1 0x18 instead of this
		}
		self.event_data_dispatch[(0x18,0x3,0x1)] = lambda dispatch_key: {
			# Sometimes get set when course starts.
			# Always gets set when a timer gets you out of the warning music
			# Can be seen multiple times, unlike time_warn
			self.message_queue.put(('event','music','normal'))
		}
		self.event_data_dispatch[(0x18,0x3,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','course','goal'))
		}
		self.event_data_dispatch[(0x18,0x3,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','course','failed'))
		}
		self.event_data_dispatch[(0x18,0x3,0x4)] = lambda dispatch_key: {
			# Warning music has started
			# Will NOT get set twice in a course
			# ie: get music warning (event sent), add +30s, music goes back to normal, get music warning again (NO EVENT SENT THIS TIME)
			self.message_queue.put(('event','music','warning'))
		}
		self.event_data_dispatch[(0x18,0x3,0x5)] = lambda dispatch_key: {
			# Done with the coin count (only if goal attained)
			self.message_queue.put(('event','course','coins_counted'))
		}

		# 0x30: Goals and ghosts
		self.event_data_dispatch[(0x30,0x1,0x0)] = lambda dispatch_key: {
			# Don't really know why there are two of these.  Ends both chomp and ghost encounters
			self.message_queue.put(('event','encounter_end','message_1'))
		}
		self.event_data_dispatch[(0x30,0x1,0x1)] = lambda dispatch_key: {
			# This should probably be message_1 but it always seems to come in second
			# Doesn't really matter because I'm not sure what these are, just that there are three of them
			self.message_queue.put(('event','encounter_start','message_2'))
		}
		# Bug?  Scanned Coin 1
		# peach event data:0x1 0x30 0x2 0x0
		self.event_data_dispatch[(0x30,0x1,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','encounter_chomp_start','message_1'))
		}

		# 0x38: Most actual events are stuffed under here

		# FIXME: Probably not toad related.  Multiplayer sync reward?  See: STEERING firing collaboration under 5.5 fw
		self.event_data_dispatch[(0x38,0x1,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','toad_trap','unlocked'))
		}

# mutiplayer, near scan of 316 (present_2 was empty code emitted (0x38,0x77,0x0))
#luigi event data:0x1 0x38 0x4 0x0

		# Player is going for a ride... SHOE, DORRIE, CLOWN, SPIN 1, SPIN 2, SPIN 3, SPIN 4, WAGGLE, HAMMER, BOMBWARP
		self.event_data_dispatch[(0x38,0x3,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','ride','in'))
		}
		self.event_data_dispatch[(0x38,0x3,0x64)] = lambda dispatch_key: {
			self.message_queue.put(('event','ride','out'))
		}

		# Bombs.  Hah, did I label these backwards?
		self.event_data_dispatch[(0x38,0x30,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','lit','BOMB 2'))
		}
		self.event_data_dispatch[(0x38,0x30,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','lit','BOB-OMB'))
		}
		self.event_data_dispatch[(0x38,0x30,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','lit','PARABOMB'))
		}
		self.event_data_dispatch[(0x38,0x30,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','lit','BOMB 3'))
		}

		self.event_data_dispatch[(0x38,0x41,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','encounter_start','message_3'))
		}

# Bug?  Scanned Coin 1
# peach event data:0x41 0x38 0x2 0x0

		self.event_data_dispatch[(0x38,0x41,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','encounter_chomp_start','message_2'))
		}

		self.event_data_dispatch[(0x38,0x42,0x0)] = lambda dispatch_key: {
			# Don't really know why there are two of these
			# Sometimes this one doesn't send
			self.message_queue.put(('event','encounter_end','message_2'))
		}

		# Not reliable
		# So unreliable I might have hallucinated this...
		# NOPE, multiplayer generated!
		#	STEERING also generates this on scan 0x1 in and scan out 0x0
		#self.event_data_dispatch[(0x38,0x50,0x0)] = lambda dispatch_key: {
		#				self.message_queue.put(('event','keyhole','out'))
		#}
		#self.event_data_dispatch[(0x38,0x50,0x1)] = lambda dispatch_key: {
		#	self.message_queue.put(('event','keyhole','in'))
		#}

		self.event_data_dispatch[(0x38,0x52,0x1)] = lambda dispatch_key: {
			# Seems to be for anything, red coins, star, P-Block, etc
			# Triggers after you eat all the CAKE or fruits (stops when the stars stop)
			self.message_queue.put(('event','music','start'))
		}
		self.event_data_dispatch[(0x38,0x52,0x0)] = lambda dispatch_key: {
			# Doesn't always trigger
			self.message_queue.put(('event','music','stop'))
		}

		self.event_data_dispatch[(0x38,0x54,0x1)] = lambda dispatch_key: {
			# Hit the programmable timer block with the timer in it (shortens the clock)
			self.message_queue.put(('event','course_clock','time_shortened'))
		}
		self.event_data_dispatch[(0x38,0x58,0x0)] = lambda dispatch_key: {
			# Getting hurt in multi by falling over.  Elicits "are you ok" from other player
			# Frozen from FREEZIE triggers this
			self.message_queue.put(('event','move','hurt'))
		}

		self.event_data_dispatch[(0x38,0x5a,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','pow','hit'))
		}

# Bored, maybe?
#mario event data:0x61 0x38 0x4 0x0
#mario event data:0x61 0x38 0x2 0x0

# After removed pants and set down prone
# peach event data:0x61 0x38 0x1 0x0

		self.event_data_dispatch[(0x38,0x61,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','prone','laying_down'))
		}

		self.event_data_dispatch[(0x38,0x61,0x3)] = lambda dispatch_key: {
			# "I'm sleepy"
			self.message_queue.put(('event','prone','sleepy'))
		}

#sleep while opening present???
#peach event data:0x61 0x38 0x7 0x0

		self.event_data_dispatch[(0x38,0x61,0x8)] = lambda dispatch_key: {
			# "oh" Usually first before sleepy, but not always.  Sometimes repeated
			# Basically, unreliable
			self.message_queue.put(('event','prone','maybe_sleep'))
		}

		self.event_data_dispatch[(0x38,0x62,0x0)] = lambda dispatch_key: {
			# kind of like noise, so maybe this is "done" doing stuff
			Mario.dp(self.system_type+" ... events ...",4)
		}

# Received during connection in conjunction with the first battery low warning, 12%, maybe related
#peach event data:0x62 0x38 0x2 0x0

		# But... WHY is this duplicated?  Don't bother sending...
		self.event_data_dispatch[(0x38,0x66,0x0)] = lambda dispatch_key: {
			# self.message_queue.put(('event','consciousness_2','asleep'))
			None
		}
		self.event_data_dispatch[(0x38,0x66,0x1)] = lambda dispatch_key: {
			# self.message_queue.put(('event','consciousness_2','awake'))
			None
		}

		self.event_data_dispatch[(0x38,0x69,0x0)] = lambda dispatch_key: {
			# Red coin 1 scanned
			self.message_queue.put(('event','red_coin',1))
		}
		self.event_data_dispatch[(0x38,0x69,0x1)] = lambda dispatch_key: {
			# FIXME: The message number matches the number on the code label+1, NOT THE VALUE HERE
			self.message_queue.put(('event','red_coin',3))
		}
		self.event_data_dispatch[(0x38,0x69,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','red_coin',2))
		}

#FIXME: finale?
#luigi event data:0x69 0x38 0x4 0x0

		# ? Block reward (duplicate of 0x4 0x40)
		self.event_data_dispatch[(0x38,0x6a,0x0)] = lambda dispatch_key: None	# 1 coin
		self.event_data_dispatch[(0x38,0x6a,0x1)] = lambda dispatch_key: None	# star
		self.event_data_dispatch[(0x38,0x6a,0x2)] = lambda dispatch_key: None	# mushroom
		# 0x3 NOT SEEN
		self.event_data_dispatch[(0x38,0x6a,0x4)] = lambda dispatch_key: None	# 5 coins
		self.event_data_dispatch[(0x38,0x6a,0x5)] = lambda dispatch_key: None	# 10 coins

		# ? Block
		self.event_data_dispatch[(0x38,0x6d,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','q_block','start'))
		}

		self.event_data_dispatch[(0x38,0x6f,0x0)] = lambda dispatch_key: {
			# Message_2 and Message_3 don't seem to be sent in multiplayer course settings?
			self.message_queue.put(('event','encounter_start','message_1'))
		}

		self.event_data_dispatch[(0x38,0x72,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','toad_trap','locked'))
		}
		self.event_data_dispatch[(0x38,0x72,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','toad_trap','start'))
		}

		self.event_data_dispatch[(0x38,0x6e,0x0)] = lambda dispatch_key: {
			# Also sent when poltergust pants are taken off
			self.message_queue.put(('event','vacuum','stop'))
		}

		# Contents of PRESENT
		self.event_data_dispatch[(0x38,0x74,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','empty'))
		}
		self.event_data_dispatch[(0x38,0x74,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','FRUIT RE'))
		}
		self.event_data_dispatch[(0x38,0x74,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','FRUIT GR'))
		}
		self.event_data_dispatch[(0x38,0x74,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','FRUIT YL'))
		}
		self.event_data_dispatch[(0x38,0x74,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','FRUIT PR'))
		}
		self.event_data_dispatch[(0x38,0x74,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','CAKE'))
		}
		self.event_data_dispatch[(0x38,0x74,0x6)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','FRUIT BL'))
		}
		self.event_data_dispatch[(0x38,0x74,0x7)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','BANANA'))
		}
		self.event_data_dispatch[(0x38,0x74,0x8)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','cookies'))
		}

		# Lost possession of whatever item you had to PRESENT
		self.event_data_dispatch[(0x38,0x75,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','food_wrapped','present'))
		}
		self.event_data_dispatch[(0x38,0x75,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','burnt_wrapped','present'))
		}
		self.event_data_dispatch[(0x38,0x75,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','poison_wrapped','present'))
		}
		self.event_data_dispatch[(0x38,0x75,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','gold_wrapped','present'))
		}

		self.event_data_dispatch[(0x38,0x76,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','multiplayer',('bad_wrapped','present')))
		}
		self.event_data_dispatch[(0x38,0x76,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','multiplayer',('food_wrapped','present')))
		}
		# umm, won't emit gold_wrapped in multiplayer?

		# Contents of PRESENT2
		self.event_data_dispatch[(0x38,0x77,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','empty'))
		}
		self.event_data_dispatch[(0x38,0x77,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','FRUIT RE'))
		}
		self.event_data_dispatch[(0x38,0x77,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','FRUIT GR'))
		}
		self.event_data_dispatch[(0x38,0x77,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','FRUIT YL'))
		}
		self.event_data_dispatch[(0x38,0x77,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','FRUIT PR'))
		}
		self.event_data_dispatch[(0x38,0x77,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','CAKE'))
		}
		self.event_data_dispatch[(0x38,0x77,0x6)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','FRUIT BL'))
		}
		self.event_data_dispatch[(0x38,0x77,0x7)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','BANANA'))
		}
		self.event_data_dispatch[(0x38,0x77,0x8)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','cookies'))
		}

		# Lost possession of whatever item you had to PRESENT 2
		self.event_data_dispatch[(0x38,0x78,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','food_wrapped','present_2'))
		}
		self.event_data_dispatch[(0x38,0x78,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','burnt_wrapped','present_2'))
		}
		self.event_data_dispatch[(0x38,0x78,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','poison_wrapped','present_2'))
		}
		self.event_data_dispatch[(0x38,0x78,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','gold_wrapped','present_2'))
		}
		# What?
		self.event_data_dispatch[(0x38,0x78,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','gold_wrapped_2','present_2'))
		}

		self.event_data_dispatch[(0x38,0x79,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','multiplayer',('bad_wrapped','present_2')))
		}

# gold wrapped multi event???
#luigi event data:0x79 0x38 0x2 0x0

		self.event_data_dispatch[(0x38,0x79,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','multiplayer',('food_wrapped','present_2')))
		}
		# umm, won't emit gold_wrapped in multiplayer?

		# All 'lost' events are sent... unreliably
		self.event_data_dispatch[(0x38,0x7c,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','lost','FRUIT RE'))
		}
		self.event_data_dispatch[(0x38,0x7c,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','ate','FRUIT RE'))
		}

		self.event_data_dispatch[(0x38,0x7d,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','lost','FRUIT GR'))
		}
		self.event_data_dispatch[(0x38,0x7d,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','ate','FRUIT GR'))
		}

		self.event_data_dispatch[(0x38,0x7e,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','lost','FRUIT YL'))
		}
		self.event_data_dispatch[(0x38,0x7e,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','ate','FRUIT YL'))
		}

		self.event_data_dispatch[(0x38,0x7f,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','lost','FRUIT PR'))
		}
		self.event_data_dispatch[(0x38,0x7f,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','ate','FRUIT PR'))
		}

		self.event_data_dispatch[(0x38,0x80,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','lost','CAKE'))
		}
		self.event_data_dispatch[(0x38,0x80,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','ate','CAKE'))
		}

		# Redundant code, prefer the one in the "random" section
		self.event_data_dispatch[(0x38,0x81,0x0)] = lambda dispatch_key: None # 1 coin
		self.event_data_dispatch[(0x38,0x81,0x1)] = lambda dispatch_key: None # star
		self.event_data_dispatch[(0x38,0x81,0x2)] = lambda dispatch_key: None # mushroom
		# 0x3 Not seen
		self.event_data_dispatch[(0x38,0x81,0x4)] = lambda dispatch_key: None # 5 coins
		self.event_data_dispatch[(0x38,0x81,0x5)] = lambda dispatch_key: None # 10 coins

		self.event_data_dispatch[(0x38,0x82,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','nabbit','start'))
		}

		# 1 BLOCK, 2 BLOCK, 3 BLOCK
		self.event_data_dispatch[(0x38,0x86,0x0)] = lambda dispatch_key: {
			# What's funny is that you can go 3, 2 (out of order)
			# but it waits until you hit 2 if you go in this sequence: 1, 3, 2(out of order)
			# 2 first is always out of order
			self.message_queue.put(('event','number_block','out_of_order'))
		}
		self.event_data_dispatch[(0x38,0x86,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','number_block',1))
		}
		self.event_data_dispatch[(0x38,0x86,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','number_block',2))
		}
		self.event_data_dispatch[(0x38,0x86,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','number_block',3))
		}
		self.event_data_dispatch[(0x38,0x86,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','number_block','complete'))
		}

#peach event data:0x87 0x38 0x2 0x0
# Sings "la la la... do do doot doot"  bored??
#	Was sitting on green, might make a difference

		# Warming up by the fire BRTYG
		self.event_data_dispatch[(0x38,0x89,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','fire','warming'))
		}

		self.event_data_dispatch[(0x38,0x8e,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','opened','present'))
		}
		self.event_data_dispatch[(0x38,0x8e,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','MUSHROOM'))
		}
		self.event_data_dispatch[(0x38,0x8e,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','1-UP'))
		}
		self.event_data_dispatch[(0x38,0x8e,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','GOLDBONE'))
		}
		self.event_data_dispatch[(0x38,0x8e,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','present','TURNIP'))
		}

		# Got anything out of PRESENT 2
		self.event_data_dispatch[(0x38,0x8f,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','opened','present_2'))
		}
		self.event_data_dispatch[(0x38,0x8f,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','MUSHROOM'))
		}
		self.event_data_dispatch[(0x38,0x8f,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','1-UP'))
		}
		self.event_data_dispatch[(0x38,0x8f,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','GOLDBONE'))
		}
		self.event_data_dispatch[(0x38,0x8f,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_2','TURNIP'))
		}

		# They must have given up organizing this
		self.event_data_dispatch[(0x38,0x91,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','checkpoint','1 coin'))
		}
		# Large Applause
		self.event_data_dispatch[(0x38,0x91,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','checkpoint','5 coins'))
		}

		self.event_data_dispatch[(0x38,0x91,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','checkpoint','3 coins'))
		}

		self.event_data_dispatch[(0x38,0x92,0x0)] = lambda dispatch_key: {
			# Doesn't always signal
			self.message_queue.put(('event','lost','FRUIT BL'))
		}
		self.event_data_dispatch[(0x38,0x92,0x6)] = lambda dispatch_key: {
			self.message_queue.put(('event','ate','FRUIT BL'))
		}

		# threw, lost, same thing
		self.event_data_dispatch[(0x38,0x94,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','turnip','threw'))
		}

		self.event_data_dispatch[(0x38,0x95,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','lost','BANANA'))
		}

# ate or lost???
		self.event_data_dispatch[(0x38,0x95,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','lost_golden','BANANA'))
		}

		self.event_data_dispatch[(0x38,0x95,0x7)] = lambda dispatch_key: {
			self.message_queue.put(('event','ate','BANANA'))
		}

		self.event_data_dispatch[(0x38,0x99,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','lost','cookies'))
		}

		self.event_data_dispatch[(0x38,0x99,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','ate','cookies'))
		}

		# MUSIC code
		# Might be calibration time for determining who is to the "left" and who is to the "right" (typically the bird)
		self.event_data_dispatch[(0x38,0x9a,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','danceparty','ready'))
		}
		self.event_data_dispatch[(0x38,0x9a,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','danceparty','start'))
		}
		# "we did it"- peach
		self.event_data_dispatch[(0x38,0x9a,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','danceparty','complete'))
		}
		self.event_data_dispatch[(0x38,0x9a,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','danceparty','end'))
		}

		# Did they run out of room in their rubbish bin of 0x38?
		# Contents of PRESENT3
		self.event_data_dispatch[(0x39,0x90,0x0)] = lambda dispatch_key: {
			# seems to only fire after fruit received
			self.message_queue.put(('event','present_3','empty'))
		}
		self.event_data_dispatch[(0x39,0x90,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','FRUIT RE'))
		}
		self.event_data_dispatch[(0x39,0x90,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','FRUIT GR'))
		}
		self.event_data_dispatch[(0x39,0x90,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','FRUIT YL'))
		}
		self.event_data_dispatch[(0x39,0x90,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','FRUIT PR'))
		}
		self.event_data_dispatch[(0x39,0x90,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','CAKE'))
		}
		self.event_data_dispatch[(0x39,0x90,0x6)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','FRUIT BL'))
		}
		self.event_data_dispatch[(0x39,0x90,0x7)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','BANANA'))
		}
		self.event_data_dispatch[(0x39,0x90,0x8)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','cookies'))
		}

		# 'wrapped' events seem unreliably sent, but the player interprets the present correctly even if the event is lost
		self.event_data_dispatch[(0x39,0x91,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','food_wrapped','present_3'))
		}
		self.event_data_dispatch[(0x39,0x91,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','burnt_wrapped','present_3'))
		}
		self.event_data_dispatch[(0x39,0x91,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','poison_wrapped','present_3'))
		}
		self.event_data_dispatch[(0x39,0x91,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','gold_wrapped','present_3'))
		}
		# gold wrapped present 3 again???
		self.event_data_dispatch[(0x39,0x91,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','gold_wrapped_2','present_3'))
		}

		self.event_data_dispatch[(0x39,0x92,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','multiplayer',('burnt_wrapped','present_3')))
		}
		self.event_data_dispatch[(0x39,0x92,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','multiplayer',('food_wrapped','present_3')))
		}

		self.event_data_dispatch[(0x39,0x93,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','opened','present_3'))
		}

		#object contents of present 3, similar to fruit
		self.event_data_dispatch[(0x39,0x93,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','MUSHROOM'))
		}
		self.event_data_dispatch[(0x39,0x93,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','1-UP'))
		}
		self.event_data_dispatch[(0x39,0x93,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','GOLDBONE'))
		}
		self.event_data_dispatch[(0x39,0x93,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','present_3','TURNIP'))
		}

		# Randomized and customizable things?
		# Programmable ? Block #1
		self.event_data_dispatch[(0x40,0x1,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_q_1','star'))
		}
		self.event_data_dispatch[(0x40,0x1,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_q_1','poison'))
		}
		self.event_data_dispatch[(0x40,0x1,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_q_1','mushroom'))
		}
		self.event_data_dispatch[(0x40,0x1,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_q_1','10 coins'))
		}

		# Programmable ? Block #2
		self.event_data_dispatch[(0x40,0x2,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_q_2','star'))
		}
		self.event_data_dispatch[(0x40,0x2,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_q_2','poison'))
		}
		self.event_data_dispatch[(0x40,0x2,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_q_2','mushroom'))
		}
		self.event_data_dispatch[(0x40,0x2,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_q_2','10 coins'))
		}

		# Programmable Timer
		self.event_data_dispatch[(0x40,0x3,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_timer','10 seconds'))
		}
		self.event_data_dispatch[(0x40,0x3,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_timer','15 seconds'))
		}
		self.event_data_dispatch[(0x40,0x3,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_timer','30 seconds'))
		}
		self.event_data_dispatch[(0x40,0x3,0x3)] = lambda dispatch_key: {
			self.message_queue.put(('event','program_timer','clock'))	# Shortens clock to 15s on Start 60 or 90, 5s on Start 30
		}

		# Complete duplicate of 0x6a 0x38 (? BLOCK reward)
		self.event_data_dispatch[(0x40,0x4,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','q_block','1 coin'))
		}
		self.event_data_dispatch[(0x40,0x4,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','q_block','star'))
		}
		self.event_data_dispatch[(0x40,0x4,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','q_block','mushroom'))
		}
		#self.event_data_dispatch[(0x40,0x4,0x3)] = lambda dispatch_key: {
		#	self.message_queue.put(('event','q_block','NOT SEEN'))
		#}
		self.event_data_dispatch[(0x40,0x4,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','q_block','5 coins'))
		}
		self.event_data_dispatch[(0x40,0x4,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','q_block','10 coins'))
		}

		# NABBIT randomizer
		# Duplicate data in 0x81 0x38
		# Hey look, it's just like ? BLOCK
		self.event_data_dispatch[(0x40,0x6,0x0)] = lambda dispatch_key: {
			self.message_queue.put(('event','nabbit','1 coin'))
		}
		self.event_data_dispatch[(0x40,0x6,0x1)] = lambda dispatch_key: {
			self.message_queue.put(('event','nabbit','star'))
		}
		self.event_data_dispatch[(0x40,0x6,0x2)] = lambda dispatch_key: {
			self.message_queue.put(('event','nabbit','mushroom'))
		}
		#self.event_data_dispatch[(0x40,0x6,0x3)] = lambda dispatch_key: {
		#	self.message_queue.put(('event','nabbit','NOT SEEN'))
		#}
		self.event_data_dispatch[(0x40,0x6,0x4)] = lambda dispatch_key: {
			self.message_queue.put(('event','nabbit','5 coins'))
		}
		self.event_data_dispatch[(0x40,0x6,0x5)] = lambda dispatch_key: {
			self.message_queue.put(('event','nabbit','10 coins'))
		}

	# override
	async def _inital_connect_updates(self):
		# Not always sent on connect
		await self.request_name_update()
		# Definitely not sent on connect
		await self.request_version_update()
		await self.request_volume_update()

		# Use as a guaranteed init event
		await self.request_battery_update()

		#await self.interrogate_ports()

	# add message_types, got to do this...
	def _reset_event_subscription_counters(self):
		for message_type in self.message_types:
			self.BLE_event_subscriptions[message_type] = 0;
		super()._reset_event_subscription_counters()

	async def set_BLE_subscription(self, message_type, should_subscribe=True):
		if not message_type in self.BLE_event_subscriptions:
			return False

		valid_sub_name = True

		if message_type == 'event':
			# This sub includes the button, which is in super
			# Hmm, probably need to make this mario_events
			await self.set_port_subscriptions([[self.EVENTS_PORT,2,5,should_subscribe]])
		elif message_type == 'motion':
			await self.set_port_subscriptions([[self.IMU_PORT,0,5,should_subscribe]])
		elif message_type == 'gesture':
			await self.set_port_subscriptions([[self.IMU_PORT,1,5,should_subscribe]])
		elif message_type == 'scanner':
			await self.set_port_subscriptions([[self.RGB_PORT,0,5,should_subscribe]])
		elif message_type == 'pants':
			await self.set_port_subscriptions([[self.PANTS_PORT,0,5,should_subscribe]])
		else:
			valid_sub_name = False

		if valid_sub_name:
			BLE_Device.dp(f'{self.system_type} set Mario hardware messages for {message_type} to {should_subscribe}',2)

		# FIXME: _Should_ event be shared with the button in base?
		# Pass "event" down the chain
		super_valid_sub_name = await super().set_BLE_subscription(message_type, should_subscribe)
		return ( valid_sub_name or super_valid_sub_name )

	async def process_bt_message(self, bt_message):
		msg_prefix = self.system_type+" "

		mario_processed = True

		if Decoder.message_type_str[bt_message['type']] == 'port_value_single':
			if bt_message['port'] in self.port_data:
				pd = self.port_data[bt_message['port']]
				if pd['name'] == 'Mario Pants Sensor':
					self.decode_pants_data(bt_message['value'])
				elif pd['name'] == 'Mario RGB Scanner':
					self.decode_scanner_data(bt_message['value'])
				elif pd['name'] == 'Mario Tilt Sensor':
					self.decode_accel_data(bt_message['value'])
				elif pd['name'] == 'LEGO Events':
					self.decode_event_data(bt_message['value'])
				elif pd['name'] == 'Mario Alt Events':
					self.decode_alt_event_data(bt_message['value'])
				else:
					mario_processed = False
					if Mario.DEBUG >= 2:
						Mario.dp(msg_prefix+"Data on "+self.port_data[bt_message['port']]['name']+" port"+":"+" ".join(hex(n) for n in bt_message['raw']),2)
			else:
				mario_processed = False

		elif Decoder.message_type_str[bt_message['type']] == 'hub_properties':
			# Logic inversion in this branch...
			mario_processed = False

			if Decoder.hub_property_op_str[bt_message['operation']] == 'Update':
				if bt_message['property'] in Decoder.hub_property_str:
					# hat tip to https://github.com/djipko/legomario.py/blob/master/legomario.py
					if Decoder.hub_property_str[bt_message['property']] == 'Mario Volume':
						Mario.dp(msg_prefix+"Volume set to "+str(bt_message['value']),2)
						self.message_queue.put(('info','volume',bt_message['value']))
						self.volume = bt_message['value']
						mario_processed = True
		else:
			mario_processed = False

		if not mario_processed:
			return await super().process_bt_message(bt_message)
		else:
			return True

	# ---- Make data useful ----

	def decode_pants_data(self, data):
		if len(data) == 1:
			Mario.dp(self.system_type+" put on "+Mario.mario_pants_to_string(data[0])+" pants",2)
			if data[0] in self.pants_codes:
				self.message_queue.put(('pants','pants',data[0]))
			else:
				Mario.dp(self.system_type+" put on unknown pants code "+str(hex(data[0])))
		else:
			Mario.dp(self.system_type+" UNKNOWN PANTS DATA, WEIRD LENGTH OF "+len(data)+":"+" ".join(hex(n) for n in data))

	# RGB Mode 0
	def decode_scanner_data(self, data):
		if len(data) != 4:
			Mario.dp(self.system_type+" UNKNOWN SCANNER DATA, WEIRD LENGTH OF "+len(data)+":"+" ".join(hex(n) for n in data))
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
			Mario.dp(self.system_type+" UNKNOWN SCANNER DATA:"+" ".join(hex(n) for n in data))
			return

		if scantype == 'barcode':
			barcode_int = Mario.mario_bytes_to_int(data[0:2])
			# Max 16-bit signed int, Github Issue #4
			if barcode_int != 32767:
				# Happens when Black is used as a color
				code_info = Mario.get_code_info(barcode_int)
				Mario.dp(self.system_type+" scanned "+code_info['label']+" (" + code_info['barcode']+ " "+str(barcode_int)+")",2)
				self.message_queue.put(('scanner','code',(code_info['barcode'], barcode_int)))
			else:
				self.message_queue.put(('error','message','Scanned malformed code'))
		elif scantype == 'color':
			color = Mario.mario_bytes_to_solid_color(data[2:4])
			Mario.dp(self.system_type+" scanned color "+color,2)
			self.message_queue.put(('scanner','color',color))
		else:
			#scantype == 'nothing':
			Mario.dp(self.system_type+" scanned nothing",2)

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

			Mario.dp(self.system_type+" accel down "+str(ud_accel)+" accel right "+str(lr_accel)+" accel backwards "+str(fb_accel),2)

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
				Mario.dp(self.system_type+" gesture data:"+notes+" ".join(hex(n) for n in data),2)

	def decode_event_data(self, data):

		# Mode 2
		if len(data) == 4:
			#													TYP		KEY		VAL (uint16)
			#luigi Data on Mario Events port:0x8 0x0 0x45 0x3	0x9 	0x20	0x1 0x0

			event_type = data[0]
			event_key = data[1]
			value = Mario.mario_bytes_to_int(data[2:])

			decoded_something = False

			# NOTE: These seem to be organized first by key (the second number)

			# Emitted at beginning and end of course
			#peach 0X9A TYPE data:0x9a 0x38 0x3 0x0

			# scan MUSIC
			#peach 0X9A TYPE data:0x9a 0x38 0x0 0x0

			#peach scanned PICNIC
				# Select the weird three-cakes
			#peach event data:0x99 0x38 0x5 0x0

			# ate BANANA
				#peach event data:0x95 0x38 0x7 0x0

			# Static, indexable codes (set in __init__)
			dispatch_key = (event_key, event_type, value)
			if dispatch_key in self.event_data_dispatch:
				self.event_data_dispatch[dispatch_key](dispatch_key)
				decoded_something = True

			# Can't be dispatched because of using variables in value
			if event_key == 0x1:
				if event_type == 0x13:
					# Scanner port
					self.message_queue.put(('event','scanner',value))

					# Fortunately, the values here match the values of the scanner codes
					# message consumer should do this work if they care about it
					#scanner_code = Mario.get_code_info(value)
					#Mario.dp(self.system_type+" scans "+scanner_code['label'])
					decoded_something = True

				# Pants port status (numbers here are _completely_ different from the pants port)
				elif event_type == 0x15:
					if value in Mario.event_pants_codes:
						self.message_queue.put(('event','pants',Mario.event_pants_codes[value]))
						decoded_something = True
					else:
						Mario.dp(self.system_type+" event: put on unknown pants:"+str(value),2)

			elif event_key == 0x18:
				if event_type == 0x4:
					# Course clock
					self.message_queue.put(('event','course_clock',('add_seconds',value/10)))
					decoded_something = True

			elif event_key == 0x20:
				# hat tip to https://github.com/bhawkes/lego-mario-web-bluetooth/blob/master/pages/index.vue
				#Mario.dp(self.system_type+" now has "+str(value)+" coins (obtained via "+str(hex(event_type))+")",2)
				if not event_type in self.event_scanner_coinsource:
					Mario.dp(self.system_type+" unknown coin source "+str(event_type),2)
				self.message_queue.put(('event','coincount',(value, event_type)))
				decoded_something = True


			# Goals and ghosts
			elif event_key == 0x30:
				if event_type == 0x4:
					# SOMETIMES, on a successful finish, data[3] is 0x2, but most of the time it's 0x0
					# on failure, 0,1,2,3
					# 0x4 for STARTC50 ?

					# START2 failure, hit a ghost as well
					#peach unknown goal status: 601: (89,2) :0x59 0x2
					Mario.dp(self.system_type+" unknown goal status: "+str(value)+": ("+str(data[2])+","+str(data[3])+") :"+" ".join(hex(n) for n in [data[2],data[3]]),2)
					decoded_something = True

			# Last code scan count
			elif event_key == 0x37:
				if event_type == 0x12:
					self.message_queue.put(('event','last_scan_count',value))
					decoded_something = True

# 			# Most actual events are stuffed under here
			elif event_key == 0x38:
# 				# Jumps: Small and large (that make the jump noise)
# 				# 0x57 0x38 0x1 0x0		# SOMETIMES a wild 0x1 appears!
				if event_type == 0x57:
					self.message_queue.put(('event','move','jump'))
					decoded_something = True

				# Tap on the table to "walk" the player
				# Only in multiplayer?
				# You can get the players completely confused and emit (steps,1) constantly if you swap presents back and forth "too soon"
				elif event_type == 0x59:
					self.message_queue.put(('event','multiplayer',('steps',value)))
					decoded_something = True

				# Current coin count for STARTC50
				# Oddly, there's no way to tell you've _started_ this mode
				# (aside from checking the scanner code)
				# Timer blocks don't work in this mode because it counts up
				# Scanning one throws a value of 16382 (a suspicious number, but the other scanner values are correct)
				# FIXME: bad name
				elif event_type == 0x5b:
					self.message_queue.put(('event','coin50_count',value))
					decoded_something = True

				# DK RIDE
				# peach event data:0x62 0x38 0x2 0x0

				# Poltergust stop
				elif event_type == 0x6e:
					if value != 0x0:
						# Returns scanner code of ghost vacuumed
						self.message_queue.put(('event','vacuumed',value))
						decoded_something = True

				elif event_type == 0x73:
					self.message_queue.put(('event','course_clock',('timer_number',value+1)))
					decoded_something = True

				# Annoyingly unable to replicate
				elif event_type == 0x70:
					self.message_queue.put(('event','vacuum','DUNNO_WHAT'))
					decoded_something = True

			# Multiplayer coins (and a duplicate message type)
			elif event_key == 0x50:
				if event_type == 0x3:
					# 3 coins per unlock.  FIXME: Hellooo, look at the event_type value here...
					# This message shows on each player
					# FIXME: This is shows up on multiplayer dual STEERING codes with synchronous fire under 5.5 fw
					self.message_queue.put(('event','multiplayer',('trap_coincount?',value)))
					decoded_something = True

				elif event_type == 0x4:
					self.message_queue.put(('event','multiplayer',('coincount',value)))
					decoded_something = True

				elif event_type == 0x5:
					# Somehow more special coins.  Different sound
					self.message_queue.put(('event','multiplayer',('double_coincount',value)))
					decoded_something = True

				elif event_type == 0x6:
					# Both cheer "teamwork"  I guess you have to build up?  Not clear.
					# Maybe the quality of the collaborative jump sync?
					self.message_queue.put(('event','multiplayer',('triple_coincount',value)))
					decoded_something = True


# Trying to do the red coin event in multiplyer, alternating who got what coin
# This doesn't seem to work?
#mario event data:0x69 0x38 0x4 0x0

# WAGGLE 2, but not reproducible
#peach event data:0x1 0x30 0x0 0x0
#peach event data:0x42 0x38 0x0 0x0

# idle?
#mario event data:0x62 0x38 0x2 0x0
#mario event data:0x62 0x38 0x2 0x0

#course failure
#CALLBACK:('mario', 'event', 'multiplayer', ('steps', 2))
#mario unknown goal status: 301: (45,1) :0x2d 0x1
#CALLBACK:('peach', 'event', 'course', 'failed')
#peach unknown goal status: 301: (45,1) :0x2d 0x1
#mario event data:0x60 0x38 0xf 0x0
#CALLBACK:('mario', 'event', 'course', 'failed')
#CALLBACK:('peach', 'event', 'music', 'stop')
#peach event data:0x60 0x38 0x0 0x0

# idle (4 beep battery alert? Might not be.  1 beep doesn't seem to send a message.  heard four with no message)
#peach event data:0x12 0x37 0x1 0x0

# TOAD 2 while on yoshi (unable to replicate)
#peach event data:0x72 0x38 0x1 0x0

# Scanned TOAD 2 (not on yoshi)
#peach event data:0x72 0x38 0x1 0x0

# BOMB 3 scan, with the star
#peach event data:0x31 0x38 0x4 0x0

# COIN 1 or COIN 2 scan
#peach event data:0x1 0x30 0x2 0x0
#peach event data:0x41 0x38 0x2 0x0
#peach event data:0x1 0x30 0x0 0x0
#peach event data:0x42 0x38 0x0 0x0

# Start a course
# 0x72 0x38 0x2 0x0	First this
# 0x1 0x18 0x1 0x0	Then this

# Last message before powered off via button
# 0x73 0x38 0x0 0x0

# Hanging out and doing nothing with fire pants on
# 0x5e 0x38 0x0 0x0

# 0x5e 0x38 0x0 0x0		a little while after first powered on

# Dumped on app connect
# 0x1 0x19 0x3 0x0
# 0x2 0x19 0x8 0x0
# 0x10 0x19 0x1 0x0
# 0x11 0x19 0x7 0x0
# 0x80 0x1 0x0 0x0
# 0x1 0x40 0x1 0x0
# 0x2 0x40 0x1 0x0
# 0x1 0x30 0x0 0x0

# Partner powers off and the player starts searching for them?
# peach Data on Mario Alt Events port:0x8 0x0 0x45 0x4 0x2 0x0 0x2 0x0

			if not decoded_something:
				Mario.dp(self.system_type+" event data:"+" ".join(hex(n) for n in data),2)
		else:
			Mario.dp(self.system_type+" non-mode-2-style event data:"+" ".join(hex(n) for n in data),2)

		pass

	def decode_alt_event_data(self, data):
		if len(data) == 4:
			# Peach goodbye mario
			# 0x2 0x0 0x1 0x0

			# Luigi goodbye peach
			# 0x2 0x0 0x3 0x0
			action = Mario.mario_bytes_to_int(data[:2])
			if action == 2:
				player = Mario.mario_bytes_to_int(data[2:])
				if player == 1:
					self.message_queue.put(('event','multiplayer', ('goodbye', 'mario')))
				elif player == 2:
					self.message_queue.put(('event','multiplayer', ('goodbye', 'luigi')))
				elif player == 3:
					self.message_queue.put(('event','multiplayer', ('goodbye', 'peach')))
				else:
					Mario.dp(self.system_type+" unknown goodbye event for player:"+" ".join(hex(n) for n in data[2:]),2)
			else:
				Mario.dp(self.system_type+" alternate event data:"+" ".join(hex(n) for n in data),2)
		else:
			Mario.dp(self.system_type+" non-mode-0-style alternate event data:"+" ".join(hex(n) for n in data),2)

	# Override
	def decode_advertising_name(self, bt_message):
		#LEGO Mario_j_r
		name = bt_message['value']

		if name.startswith("LEGO Mario_") == False or len(name) != 14:
			# print(name.encode("utf-8").hex())
			# Four spaces after the name
			if name == "LEGO Peach    ":
				Mario.dp("Peach has no icon or color set")
			elif name == "LEGO Mario    ":
				Mario.dp("Mario has no icon or color set")
			elif name == "LEGO Luigi    ":
				Mario.dp("Luigi has no icon or color set")
			else:
				Mario.dp("Unusual advertising name set:"+name)
			return

		icon = ord(name[11])
		color = ord(name[13])

		if not icon in Mario.app_icon_names:
			Mario.dp("Unknown icon:"+str(hex(icon)))
			return

		if not color in Mario.app_icon_color_names:
			Mario.dp("Unknown icon color:"+str(hex(color)))
			return

		if Mario.DEBUG >= 2:
			color_str =  Mario.app_icon_color_names[color]
			icon_str =  Mario.app_icon_names[icon]
			Mario.dp(self.system_type+" icon is set to "+color_str+" "+icon_str,2)

		self.message_queue.put(('info','icon',(icon,color)))

	# ---- Scanner code utilities ----

	def get_code_info(barcode_int):
		info = {
			'id':barcode_int,
			'barcode':Mario.int_to_scanner_code(barcode_int)
		}
		if Mario.code_data:
			Mario.dp("Scanning database for code "+str(barcode_int)+"...",3)
			if Mario.code_data['version'] == 7:
				info = Mario.populate_code_info_version_7(info)

		if not 'label' in info:
			info['label'] = 'x_'+info['barcode']+"_"
		elif not info['label']:
			info['label'] = 'x_'+info['barcode']+"_"
		return info

	def get_label_for_scanner_code_info(barcode_str):
		if Mario.code_data:
			Mario.dp("Scanning database for code "+barcode_str+"..",3)
			if Mario.code_data['version'] == 7:
				for code in Mario.code_data['codes']:
					if code['code'] == barcode_str:
						return code['label']
		return ""

	def populate_code_info_version_7(info):
		# FIXME: Kind of a junky way to search them...
		for code in Mario.code_data['codes']:
			if code['code'] == info['barcode']:
				info['label'] = code['label']
				if 'note' in code:
					info['note'] = code['note']
				if 'use' in code:
					info['use'] = code['use']
				if 'blpns' in code:
					info['blpns'] = code['blpns']
		if not 'label' in info:
			for code in Mario.code_data['unidentified']:
				if code['code'] == info['barcode']:
					if 'label' in code:
						info['label'] = code['label']
					else:
						info['label'] = None
					if 'note' in code:
						info['note'] = code['note']
		return info

	# P(n,k) or nPr (partial permutation) where n=3 and k=7 (9-2 prefix colors) is 210,
	# corresponding to the output of 210 entries.  Actual valid codes (no black) should be
	# n=3, k=6 which is 120 that matches up to the algorithmic answer of 100
	# if you eliminate the mirrors that are generated (20).

	# That's great and all but I still can't figure out how to go directly from
	# a code in Color Base-9 to the corresponding integer due to:
	# * Last two positions invert their significance in the BR codespace
	# * Detect when blacklisted black shows up
	# * Sorting out all the mirrors
	# * Can't count straight since repetition eliminates numbers from being used
	#		https://en.wikipedia.org/wiki/Factorial_number_system
	#		The Art of Computer Programming, Volume 4, Fascicle 2: Generating All Tuples and Permutations
	#		FIXME: Revisit Bricklife's algorithm now that you realize the color numbers change on every pass and they didn't account for BR prefix, so maybe you can finish the theory now
	# So, tables it is...

	def generate_gr_codespace():
		valid_codes = 0
		forbidden_codes = 0
		mirrored_codes = 0
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
						mirrorcode = Mario.does_code_have_mirror(code)
						if mirrorcode:
							# When scanned backwards, this code will read as the BR code in mirrorcode
							# But the number returned is associated with the GR codespace
							code = code+"\t"+mirrorcode
							mirrored_codes += 1
						else:
							code = code+"\t"
							valid_codes += 1
					else:
						# Contains forbidden "color"
						# Theorized to be black through experimentation, by @tomalphin on github, coincidentally(?) colored as black by @bricklife
						# https://github.com/mutesplash/legomario/issues/4#issuecomment-1368106277
						# Other colors don't even generate bluetooth responses?
						code = "-----\t"
						forbidden_codes += 1
					mario_hex = Mario.int_to_mario_bytes(count)
					Mario.dp(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex),4)
					Mario.gr_codespace[count] = code
					count += 1
		#print("Valid GR codes :"+str(valid_codes)+" Invalid: "+str(forbidden_codes+mirrored_codes)+" ("+str(forbidden_codes)+" contain black, "+str(mirrored_codes)+" have mirrors)")
		# Valid GR codes: 100 Invalid: 110 (90 contain black, 20 have mirrors)

	def generate_br_codespace():
		valid_codes = 0
		forbidden_codes = 0
		mirrored_codes = 0
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
						mirrorcode = Mario.does_code_have_mirror(code)
						if mirrorcode:
							# When scanned "backwards" this code is equivalent to a GR code in mirrorcode
							# Ignore it because the GR code's number is the one that is returned
							code = "--M--\t"+mirrorcode
							mirrored_codes += 1
						else:
							code = code+"\t"
							valid_codes += 1
					else:
						code = "-----\t"
						forbidden_codes += 1
					mario_hex = Mario.int_to_mario_bytes(count)
					Mario.dp(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex),4)
					Mario.br_codespace[count] = code
					count += 1

		#print("Valid BR codes: "+str(valid_codes)+" Invalid: "+str(forbidden_codes+mirrored_codes)+" ("+str(forbidden_codes)+" contain black, "+str(mirrored_codes)+" have mirrors)")
		# Valid BR codes: 100 Invalid: 110 (90 contain black, 20 have mirrors)

	# Thanks to Peach misscanning (DK BLOON) BRTGL as TRPBG, my initial guess of Pink had to be hedged and I only printed a page of _half_ bad codes
	# TR support as far back App 2.6.4 firmwares (5.5, maybe earlier)
	def generate_tr_codespace():
		valid_codes = 0
		forbidden_codes = 0
		mirrored_codes = 0
		prefix = "TR"
		mario_numbers = ['B','P','?','Y','V','G','L']
		potential_position_1 = mario_numbers[:]
		# resume from the end of the GR space
		count = 421
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
						# Note order compared to GR.  I just copypasted this from BR and it aligned emprically vs using GRs
						code = prefix+p1+p3+p2
						mirrorcode = Mario.does_code_have_mirror(code)
						if mirrorcode:
							# When scanned "backwards" this code is equivalent to a GR or BR code that has T in the third position
							# Ignore it because the lowest code's number is the one that is returned (BR or GR)_
							code = "--M--\t"+mirrorcode
							mirrored_codes += 1
						else:
							code = code+"\t"
							valid_codes += 1
					else:
						code = "-----\t"
						forbidden_codes += 1
					mario_hex = Mario.int_to_mario_bytes(count)
					Mario.dp(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex),4)
					Mario.tr_codespace[count] = code
					count += 1

		#print("Valid TR codes: "+str(valid_codes)+" Invalid: "+str(forbidden_codes+mirrored_codes)+" ("+str(forbidden_codes)+" contain black, "+str(mirrored_codes)+" have mirrors)")
		# Valid TR codes: 80 Invalid: 130 (90 contain black, 40 have mirrors)

	def print_codespace():
		# i\tcode\tmirror\tlabel\tscanner hex\tbinary
		Mario.generate_codespace()
		Mario.print_gr_codespace()
		Mario.print_br_codespace()
		Mario.print_tr_codespace()

	def generate_codespace():
		if not Mario.gr_codespace:
			Mario.generate_gr_codespace()
		if not Mario.br_codespace:
			Mario.generate_br_codespace()
		if not Mario.tr_codespace:
			Mario.generate_tr_codespace()

	def print_gr_codespace():
		if not Mario.gr_codespace:
			Mario.generate_gr_codespace()
		Mario.print_cached_codespace(Mario.gr_codespace)

	def print_br_codespace():
		if not Mario.br_codespace:
			Mario.generate_br_codespace()
		Mario.print_cached_codespace(Mario.br_codespace)

	def print_tr_codespace():
		if not Mario.tr_codespace:
			Mario.generate_tr_codespace()
		Mario.print_cached_codespace(Mario.tr_codespace)

	def print_cached_codespace(codespace_cache):
		for i,c in codespace_cache.items():
			mirrorcode = ""
			splitcode = c.split('\t')
			if isinstance(splitcode, list):
				c = splitcode[0]
				if splitcode[1]:
					mirrorcode = splitcode[1]
			mario_hex = Mario.int_to_mario_bytes(i)

			c_info = Mario.get_code_info(i)
			if c == "-----":
				c_info['label'] = ""
			elif c == "--M--":
				c_info['label'] = Mario.get_label_for_scanner_code_info(mirrorcode)

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
		elif mariocode.startswith('TR'):
			if mariocode[2] == 'B':
				return 'BRT'+mariocode[4]+mariocode[3]
			elif mariocode[2] == 'G':
				return 'GRT'+mariocode[4]+mariocode[3]
			return None
		else:
			return "INVAL"

	def int_to_scanner_code(mario_int):
		Mario.generate_codespace()
		code = None
		if mario_int in Mario.br_codespace:
			code = Mario.br_codespace[mario_int]
		elif mario_int in Mario.gr_codespace:
			code = Mario.gr_codespace[mario_int]
		elif mario_int in Mario.tr_codespace:
			code = Mario.tr_codespace[mario_int]
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
		color = Mario.mario_bytes_to_int(mariobytes)
		if color in Mario.solid_colors:
			return Mario.solid_colors[color]
		else:
			return 'unknown('+str(color)+')'

	def mario_pants_to_string(mariobyte):
		if mariobyte in Mario.pants_codes:
			return Mario.pants_codes[mariobyte]
		else:
			return 'unknown('+str(hex(mariobyte))+')'

	def dp(pstr, level=1):
		if Mario.DEBUG:
			if Mario.DEBUG >= level:
				print(pstr)

	# ---- Bluetooth port writes ----

	async def set_icon(self, icon, color):
		if icon not in Mario.app_icon_ints:
			Mario.dp("ERROR: Attempted to set invalid icon:"+icon)
			return
		if color not in Mario.app_icon_color_ints:
			Mario.dp("ERROR: Attempted to set invalid color for icon:"+color)

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

		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, set_name_bytes)
		await asyncio.sleep(0.1)

	async def erase_icon(self):
		if self.system_type != 'peach':
			Mario.dp("ERROR: Don't know how to erase any player except peach")
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

		self.volume = volume

		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, set_volume_bytes)
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
		await self.client.write_gatt_char(BLE_Device.characteristic_uuid, name_update_bytes)
		await asyncio.sleep(0.1)
