import socket, json, time
skill = 'progn(RBStop() load("/home/Gent/.virtuoso-bridge/smoketok001/setup/virtuoso_setup.il"))'
try:
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
except Exception as e:
    print("ERR", repr(e))
time.sleep(2)
# 检查 65082 是否还是通（旧 daemon 是否已停、新 daemon 是否已起）
try:
    s2 = socket.create_connection(("127.0.0.1", 65082), timeout=5)
    print("65082 OPEN after switch")
    s2.close()
except Exception as e:
    print("65082 closed/refused:", type(e).__name__)
