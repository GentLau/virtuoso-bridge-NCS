from pathlib import Path
p=Path('src/transport/middle.py')
t=p.read_text(encoding='utf-8')
t=t.replace('\n            if entry is None:\n','\n')
p.write_text(t, encoding='utf-8')
print('stray lines removed')
