import pprint
import time

from core.devices.psn import PSN
from core.devices.afar import Afar
from core.devices.pna import PNA
from core.common.enums import Channel, Direction, PhaseDir, PpmState
import openpyxl

# psn = PSN(ip='192.168.1.208', port=5025)
#
# psn.connect()
#
#
# print(psn.query("syst:err?"))


# pna = PNA(ip='192.168.1.130', port=5025)
# pna.connect()
# pna.set_pulse_source_external()

#
# print(pna.get_center_freq_data())

afar = Afar(connection_type='com', com_port='com4', ip='0.0.0.0', port=5000)
afar.connect()

# pprint.pprint(afar.get_tm(bu_num=4))
# pprint.pprint(afar.get_tm(bu_num=4))
#
data = [0 for _ in range(32)]
book = openpyxl.load_workbook('Матрица атт ПРМГ.xlsx')
sheet = book.active
count = 0
bu_num = 0
for raw in sheet:
    for col in raw:
        count += 1
        val = int(col.value)
        data[count - 1] = val
        if count == 32:
            bu_num += 1
            time.sleep(0.2)
            afar.set_ppm_att_from_data(bu_num=bu_num, chanel=Channel.Receiver, direction=Direction.Horizontal, values=data)
            time.sleep(0.2)
            afar.set_ppm_att_from_data(bu_num=bu_num, chanel=Channel.Receiver, direction=Direction.Horizontal, values=data)
            count = 0

# afar.preset_task(bu_num=0)
#
#
# afar.set_beam_calb_mode(bu_num=1, beam_number=1, table_num=1, chanel=Channel.Receiver,
#                         direction=Direction.Horizontal, amount_strobs=11, with_calb=False, table_crc=b'\x00\x00\x00\x00')




# afar.set_delay(bu_num=5, chanel=Channel.Transmitter, direction=Direction.Horizontal, value=12)
# time.sleep(0.5)
# afar.set_delay(bu_num=5, chanel=Channel.Transmitter, direction=Direction.Horizontal, value=12)
# time.sleep(0.5)
# afar.set_delay(bu_num=1, chanel=Channel.Receiver, direction=Direction.Vertical, value=8)
# data= [0 for _ in range(32)]
# data[8] = 0
# data[9] = 32
# data[10] = 0
# data[11] = 32
# data[12] = 32
# data[13] = 0
# data[14] = 32
# data[15] = 0
# afar.set_phase_shifter_from_data(bu_num=1,chanel=Channel.Receiver, direction=Direction.Horizontal, values=data)
# # time.sleep(0.5)
# afar.preset_task(bu_num=1)



# time.sleep(1)
# afar.set_task(bu_num=0, number_of_beam_prd=2984, number_of_beam_prm=2984, amount_strobs=10, is_cycle=False)

