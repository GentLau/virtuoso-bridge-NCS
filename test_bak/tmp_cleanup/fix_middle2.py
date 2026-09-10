import re
from pathlib import Path
p = Path('src/transport/middle.py')
t = p.read_text(encoding='utf-8')

remote_old = re.compile(
    r'    def _remote\(self, token: str\) -> RemoteClient:\r?\n'
    r'        with self\._lock:\r?\n'
    r'            client = self\._clients\.get\(token\)\r?\n'
    r'            if client is None:\r?\n'
    r'.*?'
    r'            return client\r?\n',
    re.S,
)
remote_new = (
    '    def _remote(self, token: str) -> RemoteClient:\n'
    '        with self._lock:\n'
    '            client = self._clients.get(token)\n'
    '            if client is None:\n'
    '                entry = self._entry(token)\n'
    '                client = RemoteClient(entry, self._targets(entry))\n'
    '                self._clients[token] = client\n'
    '                self._capacity[token] = threading.BoundedSemaphore(entry.runtime.thread_pool_size)\n'
    '            return client\n'
)
t, n1 = remote_old.subn(remote_new, t, count=1)
print('remote replaced', n1)

acquire_old = re.compile(
    r'    def _acquire\(self, token: str\) -> bool:\r?\n.*?return sem\.acquire\(blocking=False\)\r?\n',
    re.S,
)
acquire_new = (
    '    def _acquire(self, token: str, entry=None) -> bool:\n'
    '        if entry is None:\n'
    '            entry = self._entry(token)\n'
    '        with self._lock:\n'
    '            sem = self._capacity.get(token)\n'
    '            if sem is None:\n'
    '                sem = threading.BoundedSemaphore(entry.runtime.thread_pool_size)\n'
    '                self._capacity[token] = sem\n'
    '        return sem.acquire(blocking=False)\n'
)
t, n2 = acquire_old.subn(acquire_new, t, count=1)
print('acquire replaced', n2)

p.write_text(t, encoding='utf-8')
