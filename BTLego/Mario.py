import asyncio
from queue import SimpleQueue
from collections.abc import Iterable

import json

from bleak import BleakClient

from .BLE_Device import BLE_Device
from .Decoder import Decoder
from .MarioScanspace import MarioScanspace

from .LPF_Devices.HP_MarioVolume import MarioVolume

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

	device_has_properties = BLE_Device.device_has_properties + (
		MarioVolume,
	)

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

	# reverse map some dicts so you can index them either way
	app_icon_ints = dict(map(reversed, app_icon_names.items()))
	app_icon_color_ints = dict(map(reversed, app_icon_color_names.items()))

	def __init__(self,advertisement_data=None):
		super().__init__(advertisement_data)

		self.mode_probe_ignored_info_types = ( 0x7, 0x8 )	# Doesn't support motor bias or capability bits

		# Mario defaults to this
#		self.volume = 100

		# Translates static event sequences into messages
		self.event_data_dispatch = {
		}
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

	# Override
	async def _process_bt_message(self, bt_message):
		msg_prefix = self.system_type+" "
		mario_processed = True

		if Decoder.message_type_str[bt_message['type']] == 'port_value_single':

			device = None
			for port in self.ports:
				if bt_message['port'] == port:
					device = self.ports[port]
					break

			if device:
				if device.name == 'Mario Pants Sensor' or device.name == 'Mario Tilt Sensor' or device.name == 'Mario RGB Scanner':
					message = device.decode_pvs(bt_message['port'], bt_message['value'])
					if message:
						if len(message) == 3:
							self.message_queue.put(message)
						else:
							# SHOULD be a No-op
							pass
				elif device.name == 'LEGO Events':
					self._decode_event_data(bt_message['value'])
				elif device.name == 'Mario Alt Events':
					self._decode_alt_event_data(bt_message['value'])
				else:
					mario_processed = False
					if Mario.DEBUG >= 2:
						Mario.dp(f'{msg_prefix}Data on {device.name} port'+":"+" ".join(hex(n) for n in bt_message['raw']),2)
			else:
				Mario.dp(msg_prefix+"WARN: Received data for unconfigured port "+str(bt_message['port'])+':'+bt_message['readable'])
				mario_processed = False

# 		elif Decoder.message_type_str[bt_message['type']] == 'hub_properties':
# 			# Logic inversion in this branch...
# 			mario_processed = False
#
# 			if Decoder.hub_property_op_str[bt_message['operation']] == 'Update':
# 				if bt_message['property'] in Decoder.hub_property_str:
# 					# hat tip to https://github.com/djipko/legomario.py/blob/master/legomario.py
# 					if Decoder.hub_property_str[bt_message['property']] == 'Mario Volume':
# 						Mario.dp(msg_prefix+"Volume set to "+str(bt_message['value']),2)
# 						self.message_queue.put(('info','volume',bt_message['value']))
# 						self.volume = bt_message['value']
# 						mario_processed = True
		else:
			mario_processed = False

		if not mario_processed:
			return await super()._process_bt_message(bt_message)
		else:
			return True

	# ---- Make data useful ----

	def _decode_event_data(self, data):

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

					# FIXME: Wait, what, last past me just dumped this instead of using the same pathway as the scanner?
					# I guess this isn't... terrible? Since now they're going to be in different classes

					# Fortunately, the values here match the values of the scanner codes
					# message consumer should do this work if they care about it
					#scanner_code = MarioScanspace.get_code_info(value)
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

	def _decode_alt_event_data(self, data):
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
	def _decode_advertising_name(self, bt_message):
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

	# ---- Random stuff ----

	# Probably useful instead of having to remember to do this when working with bluetooth
	def mario_bytes_to_int(mario_byte_array):
		return int.from_bytes(mario_byte_array, byteorder="little")

	# Not useful anywhere but here, IMO
	# what is this, uint16?  put this in the base
	def int_to_mario_bytes(mario_int):
		return mario_int.to_bytes(2, byteorder="little")

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
