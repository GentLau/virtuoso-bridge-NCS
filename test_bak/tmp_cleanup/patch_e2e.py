from pathlib import Path
p=Path('tb/e2e/test_e2e_live.py')
t=p.read_text(encoding='utf-8')
old='''        s = socket.create_connection(("127.0.0.1", 16599), timeout=25)
        skill = f'progn(RBStop() load("{setup}"))'
        payload = {"skill": skill, "timeout": 25, "token": token, "log_level": "all", "log_max_bytes": 65536}
        s.sendall(json.dumps(payload).encode())
        s.shutdown(socket.SHUT_WR)
        try:
            while s.recv(65536):
                pass
        except OSError:
            pass'''
new='''        s = socket.create_connection(("127.0.0.1", 16599), timeout=25)
        try:
            skill = f'progn(RBStop() load("{setup}"))'
            payload = {"skill": skill, "timeout": 25, "token": token, "log_level": "all", "log_max_bytes": 65536}
            s.sendall(json.dumps(payload).encode())
            s.shutdown(socket.SHUT_WR)
            try:
                while s.recv(65536):
                    pass
            except OSError:
                pass
        finally:
            s.close()'''
assert old in t
t=t.replace(old,new)
p.write_text(t, encoding='utf-8')
print('e2e cleanup fixed')
