from pathlib import Path
p=Path('src/transport/middle.py')
lines=p.read_text(encoding='utf-8').split('\n')
# 0-based 57 -> line 58 stray, 58 -> line 59 entry
lines[57]='                entry = self._entry(token)'
lines.pop(58)
p.write_text('\n'.join(lines), encoding='utf-8')
print('skill fixed')
