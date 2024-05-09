import asyncio

from .LPF_Device import LPF_Device, Devtype
from ..Decoder import Decoder
from ..MarioScanspace import MarioScanspace

# Not actually SURE about the built-in devices fitting into the LPF2 model but whatever
class Mario_Events(LPF_Device):

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

	def __init__(self, port=-1):
		super().__init__(port)

		self.devtype = Devtype.FIXED

		self.port_id = 0x46
		self.name = Decoder.io_type_id_str[self.port_id]
							# Identifier for the type of device attached
							# Index into Decoder.io_type_id_str

		self.mode_subs = {
			# mode_number: [ delta_interval, subscribe_boolean, Mode Information Name (Section 3.20.1), tuple of generated messages when subscribed to this mode ]
			0: [ self.delta_interval, False, 'CHAL', ()],
			1: [ self.delta_interval, False, 'VERS', ()],
			2: [ self.delta_interval, False, 'EVENTS', ('event',)],
			3: [ self.delta_interval, False, 'DEBUG', ()]
		}

		# Translates static event sequences into messages
		self.event_data_dispatch = {
		}
		self.__init_data_dispatch()

	def __init_data_dispatch(self):

		# ( key, type, value)
		# NOTE: The line data is in type, key, value order, but they are reasonably grouped around keys

		# 0x0

		# When powered on and BT connected (reconnects do not seem to generate)
		self.event_data_dispatch[(0x0,0x0,0x0)] = lambda dispatch_key: ('debug', 'Events...','ready... !')

		# 0x18: General statuses?

		# Course reset
		# Happens a little while after the flag, sometimes on bootup too
		self.event_data_dispatch[(0x18,0x1,0x0)] = lambda dispatch_key: ('event','course','reset')
		# turns "ride", "music", and "vacuum" off before starting
		self.event_data_dispatch[(0x18,0x1,0x1)] = lambda dispatch_key: ('event','course','start')
		self.event_data_dispatch[(0x18,0x2,0x2)] = lambda dispatch_key: ('event','consciousness','asleep')
		self.event_data_dispatch[(0x18,0x2,0x1)] = lambda dispatch_key: ('event','consciousness','awake')
		 # Screen goes back to normal, sometimes 0x1 0x18 instead of this
		self.event_data_dispatch[(0x18,0x3,0x0)] = lambda dispatch_key: ('debug', 'Course status REALLY FINISHED')
		# Sometimes get set when course starts.
		# Always gets set when a timer gets you out of the warning music
		# Can be seen multiple times, unlike time_warn
		self.event_data_dispatch[(0x18,0x3,0x1)] = lambda dispatch_key: ('event','music','normal')
		self.event_data_dispatch[(0x18,0x3,0x2)] = lambda dispatch_key: ('event','course','goal')
		self.event_data_dispatch[(0x18,0x3,0x3)] = lambda dispatch_key: ('event','course','failed')
		# Warning music has started
		# Will NOT get set twice in a course
		# ie: get music warning (event sent), add +30s, music goes back to normal, get music warning again (NO EVENT SENT THIS TIME)
		self.event_data_dispatch[(0x18,0x3,0x4)] = lambda dispatch_key: ('event','music','warning')
		# Done with the coin count (only if goal attained)
		self.event_data_dispatch[(0x18,0x3,0x5)] = lambda dispatch_key: ('event','course','coins_counted')

		# 0x30: Goals and ghosts

		# Don't really know why there are two of these.  Ends both chomp and ghost encounters
		self.event_data_dispatch[(0x30,0x1,0x0)] = lambda dispatch_key: ('event','encounter_end','message_1')
		# This should probably be message_1 but it always seems to come in second
		# Doesn't really matter because I'm not sure what these are, just that there are three of them
		self.event_data_dispatch[(0x30,0x1,0x1)] = lambda dispatch_key: ('event','encounter_start','message_2')

		# Bug?  Scanned Coin 1
		# peach event data:0x1 0x30 0x2 0x0
		self.event_data_dispatch[(0x30,0x1,0x3)] = lambda dispatch_key: ('event','encounter_chomp_start','message_1')

		# 0x38: Most actual events are stuffed under here

		# FIXME: Probably not toad related.  Multiplayer sync reward?  See: STEERING firing collaboration under 5.5 fw
		self.event_data_dispatch[(0x38,0x1,0x3)] = lambda dispatch_key: ('event','toad_trap','unlocked')

# mutiplayer, near scan of 316 (present_2 was empty code emitted (0x38,0x77,0x0))
#luigi event data:0x1 0x38 0x4 0x0

		# Player is going for a ride... SHOE, DORRIE, CLOWN, SPIN 1, SPIN 2, SPIN 3, SPIN 4, WAGGLE, HAMMER, BOMBWARP
		self.event_data_dispatch[(0x38,0x3,0x0)] = lambda dispatch_key: ('event','ride','in')
		# Fireball bloops this
		self.event_data_dispatch[(0x38,0x3,0x64)] = lambda dispatch_key: ('event','ride','out')

		# Bombs.  Hah, did I label these backwards?
		self.event_data_dispatch[(0x38,0x30,0x1)] = lambda dispatch_key: ('event','lit','BOMB 2')
		self.event_data_dispatch[(0x38,0x30,0x2)] = lambda dispatch_key: ('event','lit','BOB-OMB')
		self.event_data_dispatch[(0x38,0x30,0x3)] = lambda dispatch_key: ('event','lit','PARABOMB')
		self.event_data_dispatch[(0x38,0x30,0x4)] = lambda dispatch_key: ('event','lit','BOMB 3')
		self.event_data_dispatch[(0x38,0x41,0x1)] = lambda dispatch_key: ('event','encounter_start','message_3')


# Bug?  Scanned Coin 1
# peach event data:0x41 0x38 0x2 0x0

		self.event_data_dispatch[(0x38,0x41,0x3)] = lambda dispatch_key: ('event','encounter_chomp_start','message_2')
		# Don't really know why there are two of these
		# Sometimes this one doesn't send
		self.event_data_dispatch[(0x38,0x42,0x0)] = lambda dispatch_key: ('event','encounter_end','message_2')

		# Not reliable
		# So unreliable I might have hallucinated this...
		# NOPE, multiplayer generated!
		#	STEERING also generates this on scan 0x1 in and scan out 0x0
		#self.event_data_dispatch[(0x38,0x50,0x0)] = lambda dispatch_key: {
		#				('event','keyhole','out')
		#}
		#self.event_data_dispatch[(0x38,0x50,0x1)] = lambda dispatch_key: {
		#	('event','keyhole','in')
		#}

		# Seems to be for anything, red coins, star, P-Block, etc
		# Triggers after you eat all the CAKE or fruits (stops when the stars stop)
		self.event_data_dispatch[(0x38,0x52,0x1)] = lambda dispatch_key: ('event','music','start')
		# Doesn't always trigger
		self.event_data_dispatch[(0x38,0x52,0x0)] = lambda dispatch_key: ('event','music','stop')
		# Hit the programmable timer block with the timer in it (shortens the clock)
		self.event_data_dispatch[(0x38,0x54,0x1)] = lambda dispatch_key: ('event','course_clock','time_shortened')
		# Getting hurt in multi by falling over.  Elicits "are you ok" from other player
		# Frozen from FREEZIE triggers this
		self.event_data_dispatch[(0x38,0x58,0x0)] = lambda dispatch_key: ('event','move','hurt')
		self.event_data_dispatch[(0x38,0x5a,0x0)] = lambda dispatch_key: ('event','pow','hit')


# Bored, maybe?  Also hit this after scanning a 1,2,3 block
#mario event data:0x61 0x38 0x4 0x0
#mario event data:0x61 0x38 0x2 0x0

# After removed pants and set down prone
# peach event data:0x61 0x38 0x1 0x0

		self.event_data_dispatch[(0x38,0x61,0x5)] = lambda dispatch_key: ('event','prone','laying_down')
		# "I'm sleepy"
		self.event_data_dispatch[(0x38,0x61,0x3)] = lambda dispatch_key: ('event','prone','sleepy')

#sleep while opening present???
#peach event data:0x61 0x38 0x7 0x0

		# "oh" Usually first before sleepy, but not always.  Sometimes repeated
		# Basically, unreliable
		self.event_data_dispatch[(0x38,0x61,0x8)] = lambda dispatch_key: ('event','prone','maybe_sleep')
		# kind of like noise, so maybe this is "done" doing stuff
		self.event_data_dispatch[(0x38,0x62,0x0)] = lambda dispatch_key: ('debug', 'idle ...','events ...')

# Received during connection in conjunction with the first battery low warning, 12%, maybe related
#peach event data:0x62 0x38 0x2 0x0

		# But... WHY is this duplicated?  Don't bother sending...
		# ('event','consciousness_2','asleep')
		self.event_data_dispatch[(0x38,0x66,0x0)] = lambda dispatch_key: ( 'noop',None,None )
		# ('event','consciousness_2','awake')
		self.event_data_dispatch[(0x38,0x66,0x1)] = lambda dispatch_key: ( 'noop',None,None )
# Returning None does this now that you've enforced message sanity
#peach  LEGO Events FAILED TO DECODE PVS DATA ON PORT 3:0x66 0x38 0x0 0x0
# So now no-op must be a tuple

		# Red coin 1 scanned
		self.event_data_dispatch[(0x38,0x69,0x0)] = lambda dispatch_key: ('event','red_coin',1)
		# FIXME: The message number matches the number on the code label+1, NOT THE VALUE HERE
		self.event_data_dispatch[(0x38,0x69,0x1)] = lambda dispatch_key: ('event','red_coin',3)
		self.event_data_dispatch[(0x38,0x69,0x2)] = lambda dispatch_key: ('event','red_coin',2)

#FIXME: finale?
#luigi event data:0x69 0x38 0x4 0x0

		# ? Block reward (duplicate of 0x4 0x40)
		self.event_data_dispatch[(0x38,0x6a,0x0)] = lambda dispatch_key: ( 'noop',None,None )	# 1 coin
		self.event_data_dispatch[(0x38,0x6a,0x1)] = lambda dispatch_key: ( 'noop',None,None )	# star
		self.event_data_dispatch[(0x38,0x6a,0x2)] = lambda dispatch_key: ( 'noop',None,None )	# mushroom
		# 0x3 NOT SEEN
		self.event_data_dispatch[(0x38,0x6a,0x4)] = lambda dispatch_key: ( 'noop',None,None )	# 5 coins
		self.event_data_dispatch[(0x38,0x6a,0x5)] = lambda dispatch_key: ( 'noop',None,None )	# 10 coins

		# ? Block
		self.event_data_dispatch[(0x38,0x6d,0x0)] = lambda dispatch_key: ('event','q_block','start')
		# Message_2 and Message_3 don't seem to be sent in multiplayer course settings?
		self.event_data_dispatch[(0x38,0x6f,0x0)] = lambda dispatch_key: ('event','encounter_start','message_1')

		self.event_data_dispatch[(0x38,0x72,0x0)] = lambda dispatch_key: ('event','toad_trap','locked')
		self.event_data_dispatch[(0x38,0x72,0x1)] = lambda dispatch_key: ('event','toad_trap','start')

		# Also sent when poltergust pants are taken off
		self.event_data_dispatch[(0x38,0x6e,0x0)] = lambda dispatch_key: ('event','vacuum','stop')

		# Contents of PRESENT
		self.event_data_dispatch[(0x38,0x74,0x0)] = lambda dispatch_key: ('event','present','empty')

		self.event_data_dispatch[(0x38,0x74,0x1)] = lambda dispatch_key: ('event','present','FRUIT RE')

		self.event_data_dispatch[(0x38,0x74,0x2)] = lambda dispatch_key: ('event','present','FRUIT GR')

		self.event_data_dispatch[(0x38,0x74,0x3)] = lambda dispatch_key: ('event','present','FRUIT YL')

		self.event_data_dispatch[(0x38,0x74,0x4)] = lambda dispatch_key: ('event','present','FRUIT PR')

		self.event_data_dispatch[(0x38,0x74,0x5)] = lambda dispatch_key: ('event','present','CAKE')

		self.event_data_dispatch[(0x38,0x74,0x6)] = lambda dispatch_key: ('event','present','FRUIT BL')

		self.event_data_dispatch[(0x38,0x74,0x7)] = lambda dispatch_key: ('event','present','BANANA')

		self.event_data_dispatch[(0x38,0x74,0x8)] = lambda dispatch_key: ('event','present','cookies')


		# Lost possession of whatever item you had to PRESENT
		self.event_data_dispatch[(0x38,0x75,0x0)] = lambda dispatch_key: ('event','food_wrapped','present')

		self.event_data_dispatch[(0x38,0x75,0x1)] = lambda dispatch_key: ('event','burnt_wrapped','present')

		self.event_data_dispatch[(0x38,0x75,0x2)] = lambda dispatch_key: ('event','poison_wrapped','present')

		self.event_data_dispatch[(0x38,0x75,0x3)] = lambda dispatch_key: ('event','gold_wrapped','present')


		self.event_data_dispatch[(0x38,0x76,0x1)] = lambda dispatch_key: ('event','multiplayer',('bad_wrapped','present'))

		# umm, won't emit gold_wrapped in multiplayer?
		self.event_data_dispatch[(0x38,0x76,0x3)] = lambda dispatch_key: ('event','multiplayer',('food_wrapped','present'))


		# Contents of PRESENT2
		self.event_data_dispatch[(0x38,0x77,0x0)] = lambda dispatch_key: ('event','present_2','empty')
		self.event_data_dispatch[(0x38,0x77,0x1)] = lambda dispatch_key: ('event','present_2','FRUIT RE')
		self.event_data_dispatch[(0x38,0x77,0x2)] = lambda dispatch_key: ('event','present_2','FRUIT GR')
		self.event_data_dispatch[(0x38,0x77,0x3)] = lambda dispatch_key: ('event','present_2','FRUIT YL')
		self.event_data_dispatch[(0x38,0x77,0x4)] = lambda dispatch_key: ('event','present_2','FRUIT PR')
		self.event_data_dispatch[(0x38,0x77,0x5)] = lambda dispatch_key: ('event','present_2','CAKE')
		self.event_data_dispatch[(0x38,0x77,0x6)] = lambda dispatch_key: ('event','present_2','FRUIT BL')
		self.event_data_dispatch[(0x38,0x77,0x7)] = lambda dispatch_key: ('event','present_2','BANANA')
		self.event_data_dispatch[(0x38,0x77,0x8)] = lambda dispatch_key: ('event','present_2','cookies')


		# Lost possession of whatever item you had to PRESENT 2
		self.event_data_dispatch[(0x38,0x78,0x0)] = lambda dispatch_key: ('event','food_wrapped','present_2')

		self.event_data_dispatch[(0x38,0x78,0x1)] = lambda dispatch_key: ('event','burnt_wrapped','present_2')

		self.event_data_dispatch[(0x38,0x78,0x2)] = lambda dispatch_key: ('event','poison_wrapped','present_2')

		self.event_data_dispatch[(0x38,0x78,0x3)] = lambda dispatch_key: ('event','gold_wrapped','present_2')

		# What?
		self.event_data_dispatch[(0x38,0x78,0x4)] = lambda dispatch_key: ('event','gold_wrapped_2','present_2')


		self.event_data_dispatch[(0x38,0x79,0x1)] = lambda dispatch_key: ('event','multiplayer',('bad_wrapped','present_2'))


# gold wrapped multi event???
#luigi event data:0x79 0x38 0x2 0x0

		self.event_data_dispatch[(0x38,0x79,0x3)] = lambda dispatch_key: ('event','multiplayer',('food_wrapped','present_2'))

		# umm, won't emit gold_wrapped in multiplayer?

#peach event data:0x7c 0x38 0x8 0x0
		# All 'lost' events are sent... unreliably
		self.event_data_dispatch[(0x38,0x7c,0x0)] = lambda dispatch_key: ('event','lost','FRUIT RE')

		self.event_data_dispatch[(0x38,0x7c,0x1)] = lambda dispatch_key: ('event','ate','FRUIT RE')


		self.event_data_dispatch[(0x38,0x7d,0x0)] = lambda dispatch_key: ('event','lost','FRUIT GR')

		self.event_data_dispatch[(0x38,0x7d,0x2)] = lambda dispatch_key: ('event','ate','FRUIT GR')


		self.event_data_dispatch[(0x38,0x7e,0x0)] = lambda dispatch_key: ('event','lost','FRUIT YL')

		self.event_data_dispatch[(0x38,0x7e,0x3)] = lambda dispatch_key: ('event','ate','FRUIT YL')


		self.event_data_dispatch[(0x38,0x7f,0x0)] = lambda dispatch_key: ('event','lost','FRUIT PR')

		self.event_data_dispatch[(0x38,0x7f,0x4)] = lambda dispatch_key: ('event','ate','FRUIT PR')


		self.event_data_dispatch[(0x38,0x80,0x0)] = lambda dispatch_key: ('event','lost','CAKE')

		self.event_data_dispatch[(0x38,0x80,0x5)] = lambda dispatch_key: ('event','ate','CAKE')


		# Redundant code, prefer the one in the "random" section
		self.event_data_dispatch[(0x38,0x81,0x0)] = lambda dispatch_key: ( 'noop',None,None ) # 1 coin
		self.event_data_dispatch[(0x38,0x81,0x1)] = lambda dispatch_key: ( 'noop',None,None ) # star
		self.event_data_dispatch[(0x38,0x81,0x2)] = lambda dispatch_key: ( 'noop',None,None ) # mushroom
		# 0x3 Not seen
		self.event_data_dispatch[(0x38,0x81,0x4)] = lambda dispatch_key: ( 'noop',None,None ) # 5 coins
		self.event_data_dispatch[(0x38,0x81,0x5)] = lambda dispatch_key: ( 'noop',None,None ) # 10 coins

		self.event_data_dispatch[(0x38,0x82,0x0)] = lambda dispatch_key: ('event','nabbit','start')


		# 1 BLOCK, 2 BLOCK, 3 BLOCK

		# What's funny is that you can go 3, 2 (out of order)
		# but it waits until you hit 2 if you go in this sequence: 1, 3, 2(out of order)
		# 2 first is always out of order
		self.event_data_dispatch[(0x38,0x86,0x0)] = lambda dispatch_key: ('event','number_block','out_of_order')
		self.event_data_dispatch[(0x38,0x86,0x1)] = lambda dispatch_key: ('event','number_block',1)
		self.event_data_dispatch[(0x38,0x86,0x2)] = lambda dispatch_key: ('event','number_block',2)
		self.event_data_dispatch[(0x38,0x86,0x3)] = lambda dispatch_key: ('event','number_block',3)
		self.event_data_dispatch[(0x38,0x86,0x5)] = lambda dispatch_key: ('event','number_block','complete')


#peach event data:0x87 0x38 0x2 0x0
# Sings "la la la... do do doot doot"  bored??
#	Was sitting on green, might make a difference

		# Warming up by the fire BRTYG
		self.event_data_dispatch[(0x38,0x89,0x0)] = lambda dispatch_key: ('event','fire','warming')

		self.event_data_dispatch[(0x38,0x8e,0x0)] = lambda dispatch_key: ('event','opened','present')
		self.event_data_dispatch[(0x38,0x8e,0x1)] = lambda dispatch_key: ('event','present','MUSHROOM')
		self.event_data_dispatch[(0x38,0x8e,0x2)] = lambda dispatch_key: ('event','present','1-UP')
		self.event_data_dispatch[(0x38,0x8e,0x3)] = lambda dispatch_key: ('event','present','GOLDBONE')
		self.event_data_dispatch[(0x38,0x8e,0x4)] = lambda dispatch_key: ('event','present','TURNIP')

		# Got anything out of PRESENT 2
		self.event_data_dispatch[(0x38,0x8f,0x0)] = lambda dispatch_key: ('event','opened','present_2')
		self.event_data_dispatch[(0x38,0x8f,0x1)] = lambda dispatch_key: ('event','present_2','MUSHROOM')
		self.event_data_dispatch[(0x38,0x8f,0x2)] = lambda dispatch_key: ('event','present_2','1-UP')
		self.event_data_dispatch[(0x38,0x8f,0x3)] = lambda dispatch_key: ('event','present_2','GOLDBONE')
		self.event_data_dispatch[(0x38,0x8f,0x4)] = lambda dispatch_key: ('event','present_2','TURNIP')

		# They must have given up organizing this
		self.event_data_dispatch[(0x38,0x91,0x0)] = lambda dispatch_key: ('event','checkpoint','1 coin')
		# Large Applause
		self.event_data_dispatch[(0x38,0x91,0x1)] = lambda dispatch_key: ('event','checkpoint','5 coins')
		self.event_data_dispatch[(0x38,0x91,0x2)] = lambda dispatch_key: ('event','checkpoint','3 coins')

		# Doesn't always signal
		self.event_data_dispatch[(0x38,0x92,0x0)] = lambda dispatch_key: ('event','lost','FRUIT BL')
		self.event_data_dispatch[(0x38,0x92,0x6)] = lambda dispatch_key: ('event','ate','FRUIT BL')

		# threw, lost, same thing
		self.event_data_dispatch[(0x38,0x94,0x0)] = lambda dispatch_key: ('event','turnip','threw')

		self.event_data_dispatch[(0x38,0x95,0x0)] = lambda dispatch_key: ('event','lost','BANANA')


#peach event data:0x95 0x38 0x1 0x0
# ate normal banana

#peach event data:0x95 0x38 0x2 0x0
# ate golden banana

# ate or lost???
		self.event_data_dispatch[(0x38,0x95,0x5)] = lambda dispatch_key: ('event','lost_golden','BANANA')
		self.event_data_dispatch[(0x38,0x95,0x7)] = lambda dispatch_key: ('event','ate','BANANA')

		self.event_data_dispatch[(0x38,0x99,0x0)] = lambda dispatch_key: ('event','lost','cookies')
		self.event_data_dispatch[(0x38,0x99,0x5)] = lambda dispatch_key: ('event','ate','cookies')


		# MUSIC code
		# Might be calibration time for determining who is to the "left" and who is to the "right" (typically the bird)
		self.event_data_dispatch[(0x38,0x9a,0x0)] = lambda dispatch_key: ('event','danceparty','ready')
		self.event_data_dispatch[(0x38,0x9a,0x1)] = lambda dispatch_key: ('event','danceparty','start')
		# "we did it"- peach
		self.event_data_dispatch[(0x38,0x9a,0x2)] = lambda dispatch_key: ('event','danceparty','complete')
		self.event_data_dispatch[(0x38,0x9a,0x3)] = lambda dispatch_key: ('event','danceparty','end')


#peach event data:0x9c 0x38 0x2 0x0
# Ate golden icecream (and also normal ice cream??)


		# Did they run out of room in their rubbish bin of 0x38?
		# Contents of PRESENT3
		self.event_data_dispatch[(0x39,0x90,0x0)] = lambda dispatch_key: ('event','present_3','empty')
			# seems to only fire after fruit received
		self.event_data_dispatch[(0x39,0x90,0x1)] = lambda dispatch_key: ('event','present_3','FRUIT RE')
		self.event_data_dispatch[(0x39,0x90,0x2)] = lambda dispatch_key: ('event','present_3','FRUIT GR')
		self.event_data_dispatch[(0x39,0x90,0x3)] = lambda dispatch_key: ('event','present_3','FRUIT YL')
		self.event_data_dispatch[(0x39,0x90,0x4)] = lambda dispatch_key: ('event','present_3','FRUIT PR')
		self.event_data_dispatch[(0x39,0x90,0x5)] = lambda dispatch_key: ('event','present_3','CAKE')
		self.event_data_dispatch[(0x39,0x90,0x6)] = lambda dispatch_key: ('event','present_3','FRUIT BL')
		self.event_data_dispatch[(0x39,0x90,0x7)] = lambda dispatch_key: ('event','present_3','BANANA')
		self.event_data_dispatch[(0x39,0x90,0x8)] = lambda dispatch_key: ('event','present_3','cookies')


		# 'wrapped' events seem unreliably sent, but the player interprets the present correctly even if the event is lost
		self.event_data_dispatch[(0x39,0x91,0x0)] = lambda dispatch_key: ('event','food_wrapped','present_3')
		self.event_data_dispatch[(0x39,0x91,0x1)] = lambda dispatch_key: ('event','burnt_wrapped','present_3')
		self.event_data_dispatch[(0x39,0x91,0x2)] = lambda dispatch_key: ('event','poison_wrapped','present_3')
		self.event_data_dispatch[(0x39,0x91,0x3)] = lambda dispatch_key: ('event','gold_wrapped','present_3')

		# gold wrapped present 3 again???
		self.event_data_dispatch[(0x39,0x91,0x4)] = lambda dispatch_key: ('event','gold_wrapped_2','present_3')
		self.event_data_dispatch[(0x39,0x92,0x1)] = lambda dispatch_key: ('event','multiplayer',('burnt_wrapped','present_3'))
		self.event_data_dispatch[(0x39,0x92,0x3)] = lambda dispatch_key: ('event','multiplayer',('food_wrapped','present_3'))
		self.event_data_dispatch[(0x39,0x93,0x0)] = lambda dispatch_key: ('event','opened','present_3')


		#object contents of present 3, similar to fruit
		self.event_data_dispatch[(0x39,0x93,0x1)] = lambda dispatch_key: ('event','present_3','MUSHROOM')
		self.event_data_dispatch[(0x39,0x93,0x2)] = lambda dispatch_key: ('event','present_3','1-UP')
		self.event_data_dispatch[(0x39,0x93,0x3)] = lambda dispatch_key: ('event','present_3','GOLDBONE')
		self.event_data_dispatch[(0x39,0x93,0x4)] = lambda dispatch_key: ('event','present_3','TURNIP')


		# Randomized and customizable things?
		# Programmable ? Block #1
		self.event_data_dispatch[(0x40,0x1,0x0)] = lambda dispatch_key: ('event','program_q_1','star')
		self.event_data_dispatch[(0x40,0x1,0x1)] = lambda dispatch_key: ('event','program_q_1','poison')
		self.event_data_dispatch[(0x40,0x1,0x2)] = lambda dispatch_key: ('event','program_q_1','mushroom')
		self.event_data_dispatch[(0x40,0x1,0x3)] = lambda dispatch_key: ('event','program_q_1','10 coins')


		# Programmable ? Block #2
		self.event_data_dispatch[(0x40,0x2,0x0)] = lambda dispatch_key: ('event','program_q_2','star')
		self.event_data_dispatch[(0x40,0x2,0x1)] = lambda dispatch_key: ('event','program_q_2','poison')
		self.event_data_dispatch[(0x40,0x2,0x2)] = lambda dispatch_key: ('event','program_q_2','mushroom')
		self.event_data_dispatch[(0x40,0x2,0x3)] = lambda dispatch_key: ('event','program_q_2','10 coins')


		# Programmable Timer
		self.event_data_dispatch[(0x40,0x3,0x0)] = lambda dispatch_key: ('event','program_timer','10 seconds')
		self.event_data_dispatch[(0x40,0x3,0x1)] = lambda dispatch_key: ('event','program_timer','15 seconds')
		self.event_data_dispatch[(0x40,0x3,0x2)] = lambda dispatch_key: ('event','program_timer','30 seconds')
		# Shortens clock to 15s on Start 60 or 90, 5s on Start 30
		self.event_data_dispatch[(0x40,0x3,0x3)] = lambda dispatch_key: ('event','program_timer','clock')


		# Complete duplicate of 0x6a 0x38 (? BLOCK reward)
		self.event_data_dispatch[(0x40,0x4,0x0)] = lambda dispatch_key: ('event','q_block','1 coin')
		self.event_data_dispatch[(0x40,0x4,0x1)] = lambda dispatch_key: ('event','q_block','star')
		self.event_data_dispatch[(0x40,0x4,0x2)] = lambda dispatch_key: ('event','q_block','mushroom')
		#self.event_data_dispatch[(0x40,0x4,0x3)] = lambda dispatch_key: ('event','q_block','NOT SEEN')
		self.event_data_dispatch[(0x40,0x4,0x4)] = lambda dispatch_key: ('event','q_block','5 coins')
		self.event_data_dispatch[(0x40,0x4,0x5)] = lambda dispatch_key: ('event','q_block','10 coins')

		# NABBIT randomizer
		# Duplicate data in 0x81 0x38
		# Hey look, it's just like ? BLOCK
		self.event_data_dispatch[(0x40,0x6,0x0)] = lambda dispatch_key: ('event','nabbit','1 coin')
		self.event_data_dispatch[(0x40,0x6,0x1)] = lambda dispatch_key: ('event','nabbit','star')
		self.event_data_dispatch[(0x40,0x6,0x2)] = lambda dispatch_key: ('event','nabbit','mushroom')
		#self.event_data_dispatch[(0x40,0x6,0x3)] = lambda dispatch_key: ('event','nabbit','NOT SEEN')
		self.event_data_dispatch[(0x40,0x6,0x4)] = lambda dispatch_key: ('event','nabbit','5 coins')
		self.event_data_dispatch[(0x40,0x6,0x5)] = lambda dispatch_key: ('event','nabbit','10 coins')


	def decode_pvs(self, port, data):
		# Mode 2
		if len(data) == 4:
			#													TYP		KEY		VAL (uint16)
			#luigi Data on Mario Events port:0x8 0x0 0x45 0x3	0x9 	0x20	0x1 0x0

			event_type = data[0]
			event_key = data[1]
			value = int.from_bytes(data[2:], byteorder="little")

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
				return self.event_data_dispatch[dispatch_key](dispatch_key)

			# Can't be dispatched because of using variables in value
			if event_key == 0x1:
				if event_type == 0x13:
					# Scanner port
					return ('event','scanner',value)

					# FIXME: Wait, what, last past me just dumped this instead of using the same pathway as the scanner?
					# I guess this isn't... terrible? Since now they're going to be in different classes

					# Fortunately, the values here match the values of the scanner codes
					# message consumer should do this work if they care about it
					#scanner_code = MarioScanspace.get_code_info(value)
					#print(self.system_type+" scans "+scanner_code['label'])

				# Pants port status (numbers here are _completely_ different from the pants port)
				elif event_type == 0x15:
					if value in Mario.event_pants_codes:
						return ('event','pants',Mario.event_pants_codes[value])
					else:
						return ('unknown', f'Event: put on unknown pants:{value}')

			elif event_key == 0x18:
				if event_type == 0x4:
					# Course clock
					return ('event','course_clock',('add_seconds',value/10) )

			elif event_key == 0x20:
				# hat tip to https://github.com/bhawkes/lego-mario-web-bluetooth/blob/master/pages/index.vue
				#print(self.system_type+" now has "+str(value)+" coins (obtained via "+str(hex(event_type))+")",2)
				if not event_type in MarioScanspace.event_scanner_coinsource:
					return ('unknown', f'Unknown coin source {event_type}')
				else:
					# Value is the TOTAL COUNT of the coins from the event_type
					return ('event','coincount',(value, event_type))

			# Goals and ghosts
			elif event_key == 0x30:
				if event_type == 0x4:
					# SOMETIMES, on a successful finish, data[3] is 0x2, but most of the time it's 0x0
					# on failure, 0,1,2,3
					# 0x4 for STARTC50 ?

					# START2 failure, hit a ghost as well
					#peach unknown goal status: 601: (89,2) :0x59 0x2

					# START failure, hit SNAGGLES
					#peach unknown goal status: 601: (89,2) :0x59 0x2
					return ('unknown', f'Unknown goal status: {value}: ({data[2]},{data[3]}) :'+" ".join(hex(n) for n in [data[2],data[3]]) )

			# Last code scan count
			elif event_key == 0x37:
				if event_type == 0x12:
					return ('event','last_scan_count',value)

# 			# Most actual events are stuffed under here
			elif event_key == 0x38:
# 				# Jumps: Small and large (that make the jump noise)
# 				# 0x57 0x38 0x1 0x0		# SOMETIMES a wild 0x1 appears!
				if event_type == 0x57:
					return ('event','move','jump')

				# Tap on the table to "walk" the player
				# Only in multiplayer?
				# You can get the players completely confused and emit (steps,1) constantly if you swap presents back and forth "too soon"
				elif event_type == 0x59:
					return ('event','multiplayer',('steps',value) )

				# Current coin count for STARTC50
				# Oddly, there's no way to tell you've _started_ this mode
				# (aside from checking the scanner code)
				# Timer blocks don't work in this mode because it counts up
				# Scanning one throws a value of 16382 (a suspicious number, but the other scanner values are correct)
				# FIXME: bad name
				elif event_type == 0x5b:
					return ('event','coin50_count',value)

				# DK RIDE
				# peach event data:0x62 0x38 0x2 0x0

				# Poltergust stop
				elif event_type == 0x6e:
					if value != 0x0:
						# Returns scanner code of ghost vacuumed
						return ('event','vacuumed',value)

				elif event_type == 0x73:
					return ('event','course_clock',('timer_number',value+1))

				# Annoyingly unable to replicate
				elif event_type == 0x70:
					return ('event','vacuum','DUNNO_WHAT')

			# Multiplayer coins (and a duplicate message type)
			elif event_key == 0x50:
				if event_type == 0x3:
					# 3 coins per unlock.  FIXME: Hellooo, look at the event_type value here...
					# This message shows on each player
					# FIXME: This is shows up on multiplayer dual STEERING codes with synchronous fire under 5.5 fw
					('event','multiplayer',('trap_coincount?',value) )

				elif event_type == 0x4:
					return ('event','multiplayer',('coincount',value) )

				elif event_type == 0x5:
					# Somehow more special coins.  Different sound
					return ('event','multiplayer',('double_coincount',value) )
					decoded_something = True

				elif event_type == 0x6:
					# Both cheer "teamwork"  I guess you have to build up?  Not clear.
					# Maybe the quality of the collaborative jump sync?
					return ('event','multiplayer',('triple_coincount',value) )


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

# Multiplayer connected
# mario event data:0x93 0x38 0x0 0x0
# peach event data:0x93 0x38 0x0 0x0
# mario event data:0x8b 0x38 0x0 0x0
# mario event data:0x94 0x39 0x0 0x0
# peach event data:0x8b 0x38 0x0 0x0
# peach event data:0x94 0x39 0x0 0x0
# mario event data:0x7a 0x38 0x0 0x0
# peach event data:0x7b 0x38 0x0 0x0
# mario event data:0x7b 0x38 0x0 0x0
# peach event data:0x8c 0x38 0x0 0x0
# mario event data:0x8c 0x38 0x0 0x0
# peach event data:0x8d 0x38 0x0 0x0
# mario event data:0x8d 0x38 0x0 0x0
# peach event data:0x7a 0x38 0x0 0x0

# Peach presses button last
# peach event data:0x93 0x38 0x0 0x0
# mario event data:0x93 0x38 0x0 0x0
# peach event data:0x8b 0x38 0x0 0x0
# mario event data:0x8b 0x38 0x0 0x0
# peach event data:0x94 0x39 0x0 0x0
# mario event data:0x94 0x39 0x0 0x0
# peach event data:0x7a 0x38 0x0 0x0
# mario event data:0x7b 0x38 0x0 0x0
# peach event data:0x7b 0x38 0x0 0x0
# mario event data:0x8c 0x38 0x0 0x0
# peach event data:0x8c 0x38 0x0 0x0
# mario event data:0x8d 0x38 0x0 0x0
# peach event data:0x8d 0x38 0x0 0x0
# mario event data:0x7a 0x38 0x0 0x0

			if not decoded_something:
				return ('info', 'unknown', 'Event data:'+" ".join(hex(n) for n in data) )
		else:
			return ('info', 'unknown', 'Event data: non-mode-2-style:'+" ".join(hex(n) for n in data) )
			# During mario/peach multiplayer connection
			#mario non-mode-2-style event data:0xd6 0x0 0x1 0x80 0xd6 0x0 0x1 0x80 0xd6 0x0 0x1 0x80 0x2d 0x0 0x2d 0x0

			# Peach last to push button
			#peach non-mode-2-style event data:0xc 0x0 0x1 0x80 0xc 0x0 0x1 0x80 0xc 0x0 0x1 0x80 0x2d 0x0 0x2d 0x0
