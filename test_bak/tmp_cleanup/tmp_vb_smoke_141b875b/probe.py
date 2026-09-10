import socket, json
for payload in (
    {"skill": "1+2", "timeout": 20, "token": "smoketok001", "log_level": "all", "log_max_bytes": 65536},
    {"skill": "getVersion()", "timeout": 20, "token": "wrong-token", "log_level": "all", "log_max_bytes": 65536},
):
    s = socket.create_connection(("127.0.0.1", 65082), timeout=25)
    s.sendall(json.dumps(payload).encode())
    s.shutdown(socket.SHUT_WR)
    data = b""
    while True:
        c = s.recv(65536)
        if not c:
            break
        data += c
    print("REQ", payload.get("skill"), "TOKEN", payload.get("token"))
    print(repr(data.decode("utf-8", "ignore")))
