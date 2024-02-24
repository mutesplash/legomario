from .LPF_Device import LPF_Device
from . import *
from ..Decoder import LDev

#-----

def LPF_class_for_type_id(type_id):
	# io_type_id_str indicies
	dev_classes = {
		0x2:'TrainMotor',
		0x8:'LED',
		0x14:'Voltage',
		0x15:'Current',
		LDev.RGB:'RGB',		# FIXME: More of this, right?
		0x22:'Tilt',
		0x23:'Motion',
		0x25:'Vision',
		0x27:'BoostHubMotor',
		0x26:'BoostMotor',
		0x29:'DT_Motor',
		0x2a:'DT_Beeper',
		0x2b:'DT_ColorSensor',
		0x2c:'DT_Speed',
		0x2e:'ControlPlusLarge',
		0x30:'AngularMediumAzure',
		0x36:'PUH_IMU_Gesture',
		0x37:'Controller_Buttons',
		0x38:'PUH_BT_RSSI',
		0x39:'PUH_IMU_Accel',
		0x3a:'PUH_IMU_Gyro',
		0x3b:'PUH_IMU_Position',
		0x3c:'PUH_IMU_Temp',
		0x3d:'Color',
		0x3e:'UltraDist',
		0x3f:'Force',
		0x40:'Matrix',
		0x41:'AngularSmall',
		0x46:'Mario_Events',
		0x47:'Mario_Tilt',
		0x49:'Mario_Scanner',
		0x4a:'Mario_Pants',
		0x4b:'AngularMediumGray',
		0x4c:'AngularLargeGray',
		0x55:'Mario_Alt_Events'
	}

	if type_id in dev_classes:
		return dev_classes[type_id]
	else:
		# Ha ha ha, ANYTHING IS A DEVICE!
		return 'LPF_Device'
