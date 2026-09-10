import re
from pathlib import Path
p = Path('src/transport/middle.py')
t = p.read_text(encoding='utf-8')
old = re.compile(r'        if not self\._acquire\(token\):\r?\n            return (VirtuosoResult|CommandResult)\((.*?)\)\r?\n        try:\r?\n            entry = self\._entry\(token\)\r?\n')
def repl(m):
    kind, args = m.group(1), m.group(2)
    return (f'        try:\n            entry = self._entry(token)\n            if not self._acquire(token, entry):\n                return {kind}({args})\n')
t2, n = old.subn(repl, t)
print('replaced', n)
p.write_text(t2, encoding='utf-8')
