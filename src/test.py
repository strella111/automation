from core.devices.pna import PNA

pna = PNA(ip='192.168.0.12', port=5025)

pna.connect()


pna._send_data("SYST:OPT?")
pna._read_data()

