from BTLego import Mario

import os
from pathlib import Path
import json

json_code_file = "../mariocodes.json"
code_data = None
check_file = Path(os.path.expanduser(json_code_file))
if check_file.is_file():
	with open(check_file, "rb") as f:
		try:
			code_data = json.loads(f.read())
		except ValueError as e:  # also JSONDecodeError
			print("Unable to load code translation JSON:"+str(e))

if not code_data:
	print("Known code database (mariocodes.json) NOT loaded!")

mario = Mario(json_code_dict=code_data)
print("i\tcode\tmirror\tlabel\t\tscanner hex\tbinary")
print("-----------------------------------------------------------------")

Mario.print_codespace()