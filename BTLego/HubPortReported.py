class HubPortReported():

	# Set by PMI (port mode info) requests

	def __init__(self):
		self.reset_reported_info()

	def reset_reported_info(self):
		self.modes = {}	# HubPortModeInfo by mode integer
		self.mode_count = 0
		self.mode_combinations = None
		self.virtual_port_capable = False
