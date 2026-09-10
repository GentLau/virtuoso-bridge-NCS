import json, socket, sys, tempfile, threading, time, uuid
from pathlib import Path
sys.path.insert(0, 'src')
from transport.middle import BusinessServer
from transport.runtime_paths import set_working_dir

TOKEN = 'e2e-' + uuid.uuid4().hex[:8]
HOST = 'wsl-gent'
USER = 'Gent'
SCRATCH = '/home/Gent/.virtuoso-bridge'

wd = set_working_dir(Path(tempfile.mkdtemp()))
server = BusinessServer(wd)

print('1. register')
entry = server.register_user(user='e2e', token=TOKEN, host=HOST, remote_user_name=USER, scratch_root=SCRATCH)
print('   port', entry.route.skill.daemon_port, 'python', entry.expected.remote_python)

print('2. deploy')
setup = server.deploy(TOKEN, python_major=3)
print('   setup', setup)

print('3. load into CIW via existing daemon')
skill = 'progn(RBStop() load("%s"))' % setup
s = socket.create_connection(('127.0.0.1', 16591), timeout=25)
s.sendall(json.dumps({'skill': skill, 'timeout': 25, 'token': 'smoketok027', 'log_level': 'all', 'log_max_bytes': 65536}).encode())
s.shutdown(socket.SHUT_WR)
try:
    while s.recv(65536):
        pass
except Exception:
    pass
time.sleep(2)

print('4. connect')
report = server.connect(TOKEN, deploy=False, python_major=3)
print('   report', report)
assert report.ok, report

print('5. skill')
r = server.execute_skill('1+1', token=TOKEN)
print('   ', r.status, r.output, 'log_len', len(r.log))
assert r.ok and r.output.strip().strip('"') == '2'

print('6. command')
c = server.run_command('echo vb-ok', token=TOKEN)
print('   ', c)
assert c.returncode == 0 and c.stdout.strip() == 'vb-ok'

print('7. upload/download roundtrip')
local = Path(wd) / 'payload.bin'
local.write_bytes(b'hello-vb-' * 2000)
remote = f'{SCRATCH}/{TOKEN}/status/payload.bin'
u = server.upload_file(local, remote, token=TOKEN)
print('   upload', u.returncode, u.stderr)
assert u.returncode == 0, u
back = Path(wd) / 'back.bin'
d = server.download_file(remote, back, token=TOKEN)
print('   download', d.returncode, d.stderr)
assert d.returncode == 0, d
assert back.read_bytes() == local.read_bytes()

print('8. parallel')
results = {}
def run(i):
    results[i] = server.run_command('sleep 1', token=TOKEN, parallel=True).returncode
t0 = time.time()
ts = [threading.Thread(target=run, args=(i,)) for i in range(2)]
for t in ts: t.start()
for t in ts: t.join()
elapsed = time.time() - t0
print('   elapsed', elapsed, results)
assert elapsed < 1.9 and set(results.values()) == {0}

print('ALL E2E OK', TOKEN)
