import socket, json
skill = 'RBStop() load("/home/Gent/.virtuoso-bridge/smoketok001/setup/virtuoso_setup.il")'
s = socket.create_connection(("127.0.0.1", 65082), timeout=15)
s.sendall(json.dumps({"skill": skill, "timeout": 15}).encode())
s.shutdown(socket.SHUT_WR)
data = b""
while True:
    c = s.recv(65536)
    if not c:
        break
    data += c
print(repr(data.decode("utf-8", "ignore")))
