import sys
sys.path.insert(0,'src')
from transport.ssh import SSHRunner
from transport.probe import port_free_on_remote, detect_remote_python
r = SSHRunner('wsl-gent', user='Gent')
print('python', detect_remote_python(r))
for p in (65081, 65091):
    print(p, port_free_on_remote(r, p, 'python3'))
print(r.run_command("python3 - <<'PY'\nimport socket\ns=socket.socket()\ntry:\n    s.bind(('0.0.0.0', 65081))\n    s.close()\n    raise SystemExit(0)\nexcept OSError:\n    raise SystemExit(1)\nPY\n", timeout=10))
