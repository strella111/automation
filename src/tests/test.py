import socket

#pna = PNA(ip='10.10.61.32', port=5025)


conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn.connect(('10.10.61.32', 5025))


conn.send(b'*IDN?\n')
data = conn.recv(1024)
print(data)

