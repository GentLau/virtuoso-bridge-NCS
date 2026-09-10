import socket, json
def call(skill, level="all"):
    s = socket.create_connection(("127.0.0.1", 65082), timeout=25)
    payload = {"skill": skill, "timeout": 20, "token": "smoketok001", "log_level": level, "log_max_bytes": 65536}
    s.sendall(json.dumps(payload).encode()); s.shutdown(socket.SHUT_WR)
    data = b""
    while True:
        c = s.recv(65536)
        if not c: break
        data += c
    print("=== ", skill, "level", level, "===")
    print(repr(data.decode("utf-8","ignore")[:1000]))

call("progn(error(\"boom-test\") 1)", "all")
call("1+2", "error")
