import socket, json, time
skill = 'progn(RBStop() load("/home/Gent/.virtuoso-bridge/smoketok001/setup/virtuoso_setup.il"))'
try:
    s = socket.create_connection(("127.0.0.1", 65082), timeout=20)
    s.sendall(json.dumps({"skill": skill, "timeout": 20}).encode())
    s.shutdown(socket.SHUT_WR)
    data = b""
    while True:
        c = s.recv(65536)
        if not c:
            break
        data += c
    print("RESP", repr(data.decode("utf-8", "ignore")))
except Exception as e:
    print("ERR", type(e).__name__, repr(e))
