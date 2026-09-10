from pathlib import Path
p=Path('tb/integration/test_integration.py')
t=p.read_text(encoding='utf-8')

old_cap = '''    def test_thread_capacity(self):
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        reg = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="local")
        entry.runtime.thread_pool_size = 1
        reg.register("alice", entry)

        server = BusinessServer(wd)
        server._capacity["tok-1"] = __import__("threading").BoundedSemaphore(1)

        # hold the only slot
        acquired = server._acquire("tok-1")
        self.assertTrue(acquired)
        r = server.run_command("echo x", token="tok-1")
        self.assertIn("thread pool exceeded", r.stderr)
        server._release("tok-1")'''
new_cap = '''    def test_thread_capacity(self):
        import os
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        reg = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="local")
        entry.runtime.thread_pool_size = 1
        reg.register("alice", entry)

        server = BusinessServer(wd)
        slow = f'"{sys.executable}" -c "import time; time.sleep(0.5)"'
        holder = threading.Thread(target=lambda: server.run_command(slow, token="tok-1"))
        holder.start()
        time.sleep(0.1)  # let the holder take the only slot
        r = server.run_command("echo x", token="tok-1")
        self.assertIn("thread pool exceeded", r.stderr)
        holder.join()'''
assert old_cap in t, 'cap block missing'
t=t.replace(old_cap, new_cap)

old_par = '''        def run(i):
            import shlex
            cmd = shlex.join([sys.executable, "-c", "import time; time.sleep(0.5)"])
            results[i] = server.run_command(cmd, token="tok-1", parallel=True).returncode'''
new_par = '''        def run(i):
            cmd = f'"{sys.executable}" -c "import time; time.sleep(0.5)"'
            results[i] = server.run_command(cmd, token="tok-1", parallel=True).returncode'''
assert old_par in t, 'par block missing'
t=t.replace(old_par, new_par)
p.write_text(t, encoding='utf-8')
print('tests patched')
