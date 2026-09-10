from pathlib import Path
p = Path('tb/integration/test_integration.py')
t = p.read_text(encoding='utf-8')
old = '''        def run(i):
            if sys.platform == "win32":
                results[i] = server.run_command("ping -n 3 127.0.0.1 >nul", token="tok-1", parallel=True).returncode
            else:
                results[i] = server.run_command("sleep 0.5", token="tok-1", parallel=True).returncode'''
new = '''        def run(i):
            import shlex
            cmd = shlex.join([sys.executable, "-c", "import time; time.sleep(0.5)"])
            results[i] = server.run_command(cmd, token="tok-1", parallel=True).returncode'''
assert old in t, 'old block not found'
t = t.replace(old, new)
p.write_text(t, encoding='utf-8')
print('patched')
