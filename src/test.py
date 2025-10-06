import time

from core.devices.pna import PNA


pna = PNA(ip='192.168.0.12', port=5025)
pna.connect()
print(pna.get_s_param())
res = pna.get_all_meas()
pna.set_current_meas(res[0])
pna.set_standard_pulse()
pna.get_period()
pna.set_period(0.0002)
pna.get_pulse_width()






