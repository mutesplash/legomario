import json
import os
from pathlib import Path

class MarioScanspace():

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

# 	def _decode_event_data(self, data):
# 		# Mode 2
# 		if len(data) == 4:
# 			event_type = data[0]
# 			event_key = data[1]
# 			value = int.from_bytes((data[2:]), byteorder="little")
# 			dispatch_key = (event_key, event_type, value)
# 			elif event_key == 0x20:
# 				# hat tip to https://github.com/bhawkes/lego-mario-web-bluetooth/blob/master/pages/index.vue
# 				#Mario.dp(self.system_type+" now has "+str(value)+" coins (obtained via "+str(hex(event_type))+")",2)
# 				if not event_type in self.event_scanner_coinsource:
# 					Mario.dp(self.system_type+" unknown coin source "+str(event_type),2)
# 				self.message_queue.put(('event','coincount',(value, event_type)))
# 				decoded_something = True

			# Last code scan count
#			elif event_key == 0x37:
#				if event_type == 0x12:
#					self.message_queue.put(('event','last_scan_count',value))
#					decoded_something = True


	def import_codefile(codefile="../mariocodes.json"):
		check_file = Path(os.path.expanduser(codefile))
		json_code_dict = None
		if check_file.is_file():
			try:
				with open(check_file, "rb") as f:
					try:
						json_code_dict = json.loads(f.read())
					except ValueError as e:  # also JSONDecodeError
						print("Unable to load code translation JSON:"+str(e))
						return False
			except Exception as e:
				print(f'Unable to load code translation file {check_file}: {e}')
				return False
		else:
			print("Filename provided isnt' a file")
			return False

		if not json_code_dict:
			print(f'File {check_file} contains no data')
			return False

		if not MarioScanspace.code_data:
			MarioScanspace.code_data = json_code_dict
		return True

	# ---- Scanner code utilities ----

	def get_code_info(barcode_int):
		info = {
			'id':barcode_int,
			'barcode':MarioScanspace.int_to_scanner_code(barcode_int)
		}
		if MarioScanspace.code_data:
			#print("Scanning database for code "+str(barcode_int)+"...")
			if MarioScanspace.code_data['version'] == 7:
				info = MarioScanspace.populate_code_info_version_7(info)

		if not 'label' in info:
			info['label'] = 'x_'+info['barcode']+"_"
		elif not info['label']:
			info['label'] = 'x_'+info['barcode']+"_"
		return info

	def get_label_for_scanner_code_info(barcode_str):
		if MarioScanspace.code_data:
			#print("Scanning database for code "+barcode_str+"..",3)
			if MarioScanspace.code_data['version'] == 7:
				for code in MarioScanspace.code_data['codes']:
					if code['code'] == barcode_str:
						return code['label']
		return ""

	def populate_code_info_version_7(info):
		# FIXME: Kind of a junky way to search them...
		for code in MarioScanspace.code_data['codes']:
			if code['code'] == info['barcode']:
				info['label'] = code['label']
				if 'note' in code:
					info['note'] = code['note']
				if 'use' in code:
					info['use'] = code['use']
				if 'blpns' in code:
					info['blpns'] = code['blpns']
		if not 'label' in info:
			for code in MarioScanspace.code_data['unidentified']:
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
						mirrorcode = MarioScanspace.does_code_have_mirror(code)
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
					mario_hex = MarioScanspace.int_to_mario_bytes(count)
					# print(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex))
					MarioScanspace.gr_codespace[count] = code
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
						mirrorcode = MarioScanspace.does_code_have_mirror(code)
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
					mario_hex = MarioScanspace.int_to_mario_bytes(count)
					# print(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex))
					MarioScanspace.br_codespace[count] = code
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
						mirrorcode = MarioScanspace.does_code_have_mirror(code)
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
					mario_hex = MarioScanspace.int_to_mario_bytes(count)
					# print(str(count)+"\t"+code+"\t"+" ".join('0x{:02x}'.format(n) for n in mario_hex))
					MarioScanspace.tr_codespace[count] = code
					count += 1

		#print("Valid TR codes: "+str(valid_codes)+" Invalid: "+str(forbidden_codes+mirrored_codes)+" ("+str(forbidden_codes)+" contain black, "+str(mirrored_codes)+" have mirrors)")
		# Valid TR codes: 80 Invalid: 130 (90 contain black, 40 have mirrors)

	def print_codespace():
		# i\tcode\tmirror\tlabel\tscanner hex\tbinary
		MarioScanspace.generate_codespace()
		MarioScanspace.print_gr_codespace()
		MarioScanspace.print_br_codespace()
		MarioScanspace.print_tr_codespace()

	def generate_codespace():
		if not MarioScanspace.gr_codespace:
			MarioScanspace.generate_gr_codespace()
		if not MarioScanspace.br_codespace:
			MarioScanspace.generate_br_codespace()
		if not MarioScanspace.tr_codespace:
			MarioScanspace.generate_tr_codespace()

	def print_gr_codespace():
		if not MarioScanspace.gr_codespace:
			MarioScanspace.generate_gr_codespace()
		MarioScanspace.print_cached_codespace(MarioScanspace.gr_codespace)

	def print_br_codespace():
		if not MarioScanspace.br_codespace:
			MarioScanspace.generate_br_codespace()
		MarioScanspace.print_cached_codespace(MarioScanspace.br_codespace)

	def print_tr_codespace():
		if not MarioScanspace.tr_codespace:
			MarioScanspace.generate_tr_codespace()
		MarioScanspace.print_cached_codespace(MarioScanspace.tr_codespace)

	def print_cached_codespace(codespace_cache):
		for i,c in codespace_cache.items():
			mirrorcode = ""
			splitcode = c.split('\t')
			if isinstance(splitcode, list):
				c = splitcode[0]
				if splitcode[1]:
					mirrorcode = splitcode[1]
			mario_hex = MarioScanspace.int_to_mario_bytes(i)

			c_info = MarioScanspace.get_code_info(i)
			if c == "-----":
				c_info['label'] = ""
			elif c == "--M--":
				c_info['label'] = MarioScanspace.get_label_for_scanner_code_info(mirrorcode)

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
		MarioScanspace.generate_codespace()
		code = None
		if mario_int in MarioScanspace.br_codespace:
			code = MarioScanspace.br_codespace[mario_int]
		elif mario_int in MarioScanspace.gr_codespace:
			code = MarioScanspace.gr_codespace[mario_int]
		elif mario_int in MarioScanspace.tr_codespace:
			code = MarioScanspace.tr_codespace[mario_int]
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
		return

	# Not useful anywhere but here, IMO
	# what is this, uint16?  put this in the base
	def int_to_mario_bytes(mario_int):
		return mario_int.to_bytes(2, byteorder="little")

	def mario_bytes_to_solid_color(mariobytes):
		color =  int.from_bytes(mariobytes, byteorder="little")
		if color in MarioScanspace.solid_colors:
			return MarioScanspace.solid_colors[color]
		else:
			return 'unknown('+str(color)+')'

