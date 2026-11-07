#!/usr/bin/env python3
"""patches/busy_own_commands.py: applied to a stand-in of Hermes's busy fast-path, then each kind of typed command is tried. No Hermes, no network: python3 -I busy_own_commands_selftest.py"""
import asyncio, os, subprocess, sys, tempfile, types

here = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
STAND_IN = '''
import types
REGISTRY = {"stop", "new", "status"}
class MessageType: PHOTO = "photo"; TEXT = "text"
PLUGINS = {}
def get_plugin_command_handler(name): return PLUGINS.get(name)
class Gateway:
    _draining = False
    quick = {}
    dispatched = []
    def _hm_quick_commands(self): return self.quick
    def _check_slash_access(self, source, name): return None
    async def _dispatch_busy_slash_command(self, event, cmd, key, source): return "registry:" + cmd.name
    async def _hm_dispatch_quick_and_plugin_commands(self, event, source, command):
        self.dispatched.append(command)
        h = PLUGINS.get(command.replace("_", "-"))
        if h: return True, h(event.args), command
        if self.quick.get(command): return True, "quick:" + command, command
        return False, None, command
    def _hm_merge_pending_for_source(self, *a, **k): pass
    async def _hm_busy_slash_or_photo(self, event, source, _quick_key):
        _evt_cmd = event.get_command()
        _cmd_def_inner = types.SimpleNamespace(name=_evt_cmd) if _evt_cmd in REGISTRY else None

        if _cmd_def_inner:
            return True, await self._dispatch_busy_slash_command(event, _cmd_def_inner, _quick_key, source)

        # Telegram photo bursts arrive as near-simultaneous updates — never interrupt for a
        # photo-only follow-up; adapter-level batching absorbs them.
        if event.message_type == MessageType.PHOTO:
            self._hm_merge_pending_for_source(source, _quick_key, event)
            return True, None
        return False, None
'''
path = os.path.join(tmp, "run_inbound.py")
open(path, "w").write(STAND_IN)
fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

r = subprocess.run([sys.executable, "-I", f"{here}/patches/busy_own_commands.py", path], capture_output=True, text=True)
check("the patch applies once", r.returncode == 0 and "patched" in r.stdout)
once = open(path).read()
r = subprocess.run([sys.executable, "-I", f"{here}/patches/busy_own_commands.py", path], capture_output=True, text=True)
check("applying it again changes nothing", "already patched" in r.stdout and open(path).read() == once)
bad = os.path.join(tmp, "other.py"); open(bad, "w").write("def f(): pass\n")
r = subprocess.run([sys.executable, "-I", f"{here}/patches/busy_own_commands.py", bad], capture_output=True, text=True)
check("a Hermes that changed there makes it fail loudly", r.returncode != 0 and "expected 1 match" in (r.stderr + r.stdout))

mod = types.ModuleType("run_inbound"); exec(compile(once, path, "exec"), mod.__dict__)
fake_pkg = types.ModuleType("hermes_cli"); fake_plugins = types.ModuleType("hermes_cli.plugins")
fake_plugins.get_plugin_command_handler = lambda name: mod.PLUGINS.get(name)   # the patched block imports it from Hermes
sys.modules["hermes_cli"], sys.modules["hermes_cli.plugins"] = fake_pkg, fake_plugins
class Ev:
    def __init__(self, cmd, kind="text", args=""): self.cmd, self.message_type, self.args = cmd, kind, args
    def get_command(self): return self.cmd
def run(cmd, kind="text", *, plugins=None, quick=None, draining=False, args=""):
    g = mod.Gateway(); g._draining = draining; g.quick = quick or {}; g.dispatched = []
    mod.PLUGINS.clear(); mod.PLUGINS.update(plugins or {})
    res = asyncio.run(g._hm_busy_slash_or_photo(Ev(cmd, kind, args), None, "k"))
    return res, g.dispatched

res, d = run("parar", plugins={"parar": lambda a: "parando " + a}, args="subs")
check("a plugin command (/parar) runs while the turn is busy", res == (True, "parando subs") and d == ["parar"])
res, d = run("estado", quick={"estado": {"type": "exec"}})
check("a quick command (/estado) runs while the turn is busy", res == (True, "quick:estado"))
res, d = run("opinion", plugins={"opinion": lambda a: "ok"})
check("every plugin command, not only the control ones", res == (True, "ok"))
res, d = run("stop")
check("a registry command (/stop) takes the path it always took", res == (True, "registry:stop") and d == [])
res, d = run("nosuch")
check("an unknown /command still falls through to the model as text", res == (False, None) and d == [])
res, d = run(None)
check("plain text still falls through", res == (False, None) and d == [])
res, d = run(None, "photo")
check("a photo burst is still queued", res == (True, None))
res, d = run("parar", plugins={"parar": lambda a: "x"}, draining=True)
check("while the gateway drains, nothing new is run and the old path decides", res == (False, None) and d == [])
res, d = run("mi_cmd", plugins={"mi-cmd": lambda a: "guion"})
check("Telegram's underscore form matches a hyphenated plugin command", res == (True, "guion"))
print("\n".join(fails) or "busy_own_commands_selftest: all ok")
sys.exit(1 if fails else 0)
