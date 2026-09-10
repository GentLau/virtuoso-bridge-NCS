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
    raw = data.decode("utf-8", "ignore")
    print("=== ", skill, "level", level, "===")
    print(raw[:800])
    print("...len", len(raw))

call("1+2", "all")
call("progn(warn(\"test-warn-xyz\") 7)", "all")
call("1+2", "warn")
call("1+2", "error")
call("1+2", "off")
