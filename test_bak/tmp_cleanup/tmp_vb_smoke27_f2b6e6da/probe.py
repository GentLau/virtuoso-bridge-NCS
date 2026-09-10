import socket, json
def call(skill, token, level="all"):
    s = socket.create_connection(("127.0.0.1", 16591), timeout=25)
    payload={"skill":skill,"timeout":20,"token":token,"log_level":level,"log_max_bytes":65536}
    s.sendall(json.dumps(payload).encode()); s.shutdown(socket.SHUT_WR)
    data=b""
    while True:
        c=s.recv(65536)
        if not c: break
        data+=c
    print(skill, token, level, "=>", repr(data.decode("utf-8","ignore")[:300]))

call("1+2","smoketok027","all")
call("getVersion()","bad-token","all")
call("1+2","smoketok027","off")
