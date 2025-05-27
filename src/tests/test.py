from core.devices.pna import PNA
from core.devices.psn import PSN
from loguru import logger

pna = PNA(ip='10.10.61.32', port=5025)
psn = PSN(ip='10.10.61.30', port=5025)

pna.connect()
logger.info('PNA connected')
logger.info(pna.connection)

psn.connect()
logger.info('PSN connected')
logger.info(psn.connection)


pna.preset()
pna.set_power(1, 0)
pna.power_off()
pna.set_freq_start(9300000000)
pna.set_freq_stop(9800000000)
pna.set_freq_points(201)

psn.preset()










