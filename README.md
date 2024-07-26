# legomario

**DOES NOT WORK IF YOU FIRMWARE UPDATE MARIO FIGURES TO APP VERSION 2.9**
_Failed to update the notification status for characteristic 17: Error Domain=CBATTErrorDomain Code=5 "Authentication is insufficient."_

* Generates printable SVG scanner codes for LEGO Mario as well as Luigi & Peach.
    [View the HTML live from the repository](https://raw.githack.com/mutesplash/legomario/main/mariocodes.html)
* Provides a Python library for interacting with LEGO Bluetooth LE devices including:
	* LEGO Mario (and Luigi & Peach)
	* LEGO Powered Up Remote Control (88010)
	* DUPLO Train Hub No. 5
	* LEGO Powered Up Hub No. 4 (88009)
	* LEGO Technic Hub No. 2 (88012)
	* LEGO Boost Hub No. 1 (88006) aka Move Hub aka JAJUR1
	* Does **not** (currently) work with WeDo 2.0 Hub (45301) aka LPF2 Smart Hub 2.  This does not seem to speak standard LEGO Wireless Protocol 3.0
* Has some idea about how to communicate with all but one Lego Power Functions v2 (LPF2) devices that can be attached to the hubs
* Does not have great documentation yet, but things like "python -m pydoc BTLego.LPF_Devices.RGB" are intended to be helpful, and may even be the basis of acceptable documentation... eventually


## Requires

* [Bleak](https://github.com/hbldh/bleak)

## Try a Bluetooth example [^1]
```
git clone https://github.com/mutesplash/legomario.git
cd legomario
python3 -m venv .
```
Activate the virtual environment. In bash: `source bin/activate`
```
python3 -m pip install Bleak
cd examples
ln -s ../BTLego
python3 scan.py
```

[^1]: Python adds the script _location_ to sys.path, so to run the examples in place, link the module into /examples


