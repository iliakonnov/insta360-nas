import struct, socket
from lib_one_proto import check_authorization_pb2
s = socket.socket()
s.bind(('127.0.0.1', 0))
s.connect(('127.0.0.1', 6666))
s.sendall(b'\x0a\x00\x00\x00\x06\x00\x00syNceNdinS')
s.recv(14)

req = check_authorization_pb2.CheckAuthorization()
req.id = 'user_1'
pb_bytes = req.SerializeToString()
header = b'\x04\x00\x00' + struct.pack('<H', 39) + b'\x02' + struct.pack('<i', 1)[0:3] + b'\x80\x00\x00'
payload = header + pb_bytes
pkt_data = bytearray(struct.pack('<i', len(payload) + 4))
pkt_data.extend(payload)
s.sendall(pkt_data)

len_bytes = s.recv(4)
pkt_len = int.from_bytes(len_bytes, 'little')
resp_data = s.recv(pkt_len - 4)
print('Got auth response', len(resp_data))

import urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8080/DCIM/Camera01/') as f:
        print(f.read().decode('utf-8'))
except Exception as e:
    print('Failed HTTP request:', e)

s.close()
