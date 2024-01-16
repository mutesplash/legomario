# legomario

* Generates printable SVG scanner codes for LEGO Mario as well as Luigi & Peach.
    [View the HTML live from the repository](https://raw.githack.com/mutesplash/legomario/main/mariocodes.html)
* Provides a Python library for interacting with LEGO Bluetooth LE devices including:
	* LEGO Mario (Luigi & Peach)
	* LEGO Powered Up Remote Control (88010)
	* DUPLO Train Hub No. 5
	* Technic Hub No. 2 (88012) and (some) attached LEGO Powered Up (LPF2) Devices
* Does not have great documentation yet

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


