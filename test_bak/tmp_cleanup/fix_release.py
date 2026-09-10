from pathlib import Path
p=Path('src/transport/middle.py')
t=p.read_text(encoding='utf-8')
t=t.replace('''        try:
            entry = self._entry(token)
            if not self._acquire(token, entry):
                return VirtuosoResult(status=ExecutionStatus.ERROR, errors=["thread pool exceeded"])''','''        acquired = False
        try:
            entry = self._entry(token)
            if not self._acquire(token, entry):
                return VirtuosoResult(status=ExecutionStatus.ERROR, errors=["thread pool exceeded"])
            acquired = True''')
t=t.replace('''        try:
            entry = self._entry(token)
            if not self._acquire(token, entry):
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded")''','''        acquired = False
        try:
            entry = self._entry(token)
            if not self._acquire(token, entry):
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded")
            acquired = True''')
t=t.replace('''        finally:
            self._release(token)''','''        finally:
            if acquired:
                self._release(token)''')
p.write_text(t, encoding='utf-8')
print('release guarded')
