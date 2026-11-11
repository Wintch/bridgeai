#!/usr/bin/env python3
"""patches/busy_own_commands.py: applied to stand-ins of Hermes's busy fast-path and of the adapter's busy-session guard, then each kind of typed command is tried. No Hermes, no network: python3 -I busy_own_commands_selftest.py"""
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
ADAPTER = '''
class Adapter:
    gateway_runner = None
    def __init__(self): self.inline, self.queued = [], []
    async def _dispatch_inline_reply(self, event): self.inline.append(event.get_command())
    async def _dispatch_active_session_command(self, event, key, cmd): self.inline.append("interrupt:" + cmd)
    def _discard_text_debounce(self, key): pass
    async def _handle_message_while_active(self, event, session_key: str) -> None:
        cmd = event.get_command()
        from hermes_cli.commands import (is_interrupt_then_dispatch, should_bypass_active_session)
        if should_bypass_active_session(cmd):
            try:
                # /stop, /new, /reset: cancel + response + drain; other bypasses don't cancel.
                if cmd and is_interrupt_then_dispatch(cmd):
                    self._discard_text_debounce(session_key)
                    await self._dispatch_active_session_command(event, session_key, cmd)
                else:
                    await self._dispatch_inline_reply(event)
            except Exception as e:
                pass
            return
        self.queued.append(cmd)
'''
path = os.path.join(tmp, "run_inbound.py")
apath = os.path.join(tmp, "base.py")
open(path, "w").write(STAND_IN)
open(apath, "w").write(ADAPTER)
fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

r = subprocess.run([sys.executable, "-I", f"{here}/patches/busy_own_commands.py", path, apath], capture_output=True, text=True)
check("the patch applies once", r.returncode == 0 and "patched" in r.stdout)
once = open(path).read()
r = subprocess.run([sys.executable, "-I", f"{here}/patches/busy_own_commands.py", path, apath], capture_output=True, text=True)
check("applying it again changes nothing", "already patched" in r.stdout and open(path).read() == once and open(apath).read().count("aibridge-patch: busy_own_commands") == 1)
bad = os.path.join(tmp, "other.py"); open(bad, "w").write("def f(): pass\n")
r = subprocess.run([sys.executable, "-I", f"{here}/patches/busy_own_commands.py", bad, apath], capture_output=True, text=True)
check("a Hermes that changed there makes it fail loudly", r.returncode != 0 and "expected 1 match" in (r.stderr + r.stdout))
fresh_in, fresh_ad = os.path.join(tmp, "fresh_in.py"), os.path.join(tmp, "fresh_ad.py")
open(fresh_in, "w").write(STAND_IN); open(fresh_ad, "w").write("class Adapter:\n    pass\n")
r = subprocess.run([sys.executable, "-I", f"{here}/patches/busy_own_commands.py", fresh_in, fresh_ad], capture_output=True, text=True)
check("if one file does not match, neither is written", r.returncode != 0 and open(fresh_in).read() == STAND_IN and open(fresh_ad).read() == "class Adapter:\n    pass\n")

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

# the adapter's busy-session guard
amod = types.ModuleType("base"); exec(compile(open(apath).read(), apath, "exec"), amod.__dict__)
fake_commands = types.ModuleType("hermes_cli.commands")
fake_commands.should_bypass_active_session = lambda c: bool(c) and c in mod.REGISTRY
fake_commands.is_interrupt_then_dispatch = lambda c: c in ("stop", "new")
sys.modules["hermes_cli.commands"] = fake_commands
def arun(cmd, *, plugins=None, quick=None):
    a = amod.Adapter(); mod.PLUGINS.clear(); mod.PLUGINS.update(plugins or {})
    if quick is not None: a.gateway_runner = types.SimpleNamespace(_hm_quick_commands=lambda: quick)
    asyncio.run(a._handle_message_while_active(Ev(cmd), "k"))
    return a.inline, a.queued
check("adapter: a plugin command typed while busy runs inline (it used to be queued as text)", arun("trabajos", plugins={"trabajos": lambda a: ""}) == (["trabajos"], []))
check("adapter: a quick command typed while busy runs inline", arun("estado", quick={"estado": {"type": "exec"}}) == (["estado"], []))
check("adapter: a Hermes command is still dispatched as before (/stop interrupts, /status inline)", arun("stop") == (["interrupt:stop"], []) and arun("status") == (["status"], []))
check("adapter: an unknown command and plain text are still queued for the turn", arun("nosuch", quick={}) == ([], ["nosuch"]) and arun(None) == ([], [None]))
check("adapter: a runner without quick commands does not break plugin detection", arun("trabajos", plugins={"trabajos": lambda a: ""}, quick=None) == (["trabajos"], []))
print("\n".join(fails) or "busy_own_commands_selftest: all ok")
sys.exit(1 if fails else 0)
