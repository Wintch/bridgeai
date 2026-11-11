#!/usr/bin/env python3
"""Offline test of ops/stack_service.py: no Docker, no network. Run: python3 ops/stack_service_selftest.py"""
import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stack_service as ss  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


class R:
    def __init__(self, out="", rc=0, err=""):
        self.stdout, self.returncode, self.stderr = out, rc, err


TOKEN = "a1b2c3d4" * 8
ZBX = f"https://zabbix.example.com {TOKEN} bridgeai/tecnico"


def go(args, value, awake=True, answer=None, wake_ok=True):
    calls = []
    out, err = io.StringIO(), io.StringIO()

    def fake_run(cmd, **k):
        calls.append((cmd, k.get("input")))
        return answer or R("Guardada y comprobada: Monitoreo (Zabbix) (…" + TOKEN[-4:] + "). Ya la usa, sin reiniciar nada.\n")

    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = ss.main(args, stdin=io.StringIO((value if value is not None else "") + "\n"), run=fake_run, running=lambda n: awake,
                     wake=lambda n: wake_ok, hold=lambda n: contextlib.nullcontext())
    return rc, out.getvalue() + err.getvalue(), calls


rc, out, calls = go(["tecnico", "zabbix"], ZBX)
check("zabbix: ok, runs `gateway servicios guardar zabbix` in the stack's container", rc == 0 and "\nOK: Guardada y comprobada" in out
      and calls[0][0] == ["docker", "exec", "-i", "stack-tecnico-hermes", "gateway", "servicios", "guardar", "zabbix"], (rc, out, calls))
check("the value (with spaces) goes on stdin only, never in argv", calls[0][1] == ZBX + "\n" and TOKEN not in " ".join(calls[0][0]) and "zabbix.example.com" not in " ".join(calls[0][0]), calls)
check("the token is not in what the script printed", TOKEN not in out)
rc, out, calls = go(["hx", "groq"], "gsk_" + "y" * 40)
check("any service goes the same way (groq)", rc == 0 and calls[0][0][-2:] == ["guardar", "groq"], (rc, out, calls))
rc, out, calls = go(["hx", "audd"], "t" * 32)
check("any service goes the same way (audd)", rc == 0 and calls[0][0][-2:] == ["guardar", "audd"], (rc, out, calls))
rc, out, calls = go(["tecnico", "zabbix"], ZBX, answer=R("No la guardé: Zabbix no aceptó el token: copialo entero.\n", 1))
check("the gateway's refusal is shown and exits 1", rc == 1 and "\nFAIL: No la guardé: Zabbix no aceptó el token" in out, (rc, out))
rc, out, calls = go(["tecnico", "zabbix"], ZBX, answer=R("echo " + TOKEN + " at https://zabbix.example.com\n", 0))
check("anything of the value that comes back is scrubbed", TOKEN not in out and "zabbix.example.com" not in out and "<value>" in out, out)
rc, out, calls = go(["tecnico", "zabbix"], ZBX, answer=R("", 1, "Traceback: boom\n"))
check("stderr is shown when stdout is empty", rc == 1 and "Traceback" in out, (rc, out))
rc, out, calls = go(["tecnico", "zabbix"], ZBX, answer=R("", 1))
check("no answer at all is a FAIL that says nothing was shown", rc == 1 and "no answer" in out and TOKEN not in out, (rc, out))
rc, out, calls = go(["tecnico", "nope"], ZBX, answer=R("Servicios: geoapify, tmdb, zabbix\n", 2))
check("an unknown service: the gateway lists the real ones, exit 1", rc == 1 and "geoapify" in out, (rc, out))
rc, out, calls = go(["tecnico", "Zabbix"], ZBX)
check("a service name with odd characters is refused before anything runs", rc == 2 and not calls, out)
rc, out, calls = go(["tecnico", "zab;rm"], ZBX)
check("a shell-looking service is refused", rc == 2 and not calls, out)
rc, out, calls = go(["Bad Name", "zabbix"], ZBX)
check("a bad stack name is refused", rc == 2 and not calls, out)
rc, out, calls = go(["tecnico", "zabbix"], "")
check("an empty value is refused", rc == 2 and not calls, out)
rc, out, calls = go(["tecnico", "zabbix"], "x" * 701)
check("an over-long value is refused", rc == 2 and not calls, out)
rc, out, calls = go(["tecnico", "zabbix"], "a\x01b")
check("a control character is refused", rc == 2 and not calls, out)
rc, out, calls = go(["tecnico"], ZBX)
check("missing service: usage, exit 2", rc == 2 and not calls, out)
rc, out, calls = go(["tecnico", "zabbix", "--bogus"], ZBX)
check("an unknown flag is refused", rc == 2 and not calls, out)
rc, out, calls = go(["tecnico", "zabbix"], ZBX, awake=False)
check("an asleep stack is started, the user is told, and the value is then stored", rc == 0 and calls and "asleep: starting it" in out, (rc, out))
rc, out, calls = go(["tecnico", "zabbix"], ZBX, awake=False, wake_ok=False)
check("if the stack cannot be started nothing is sent", rc == 3 and not calls and "nothing was stored" in out, (rc, out))
rc, out, calls = go(["tecnico", "zabbix", "--remove"], None, answer=R("Quitada: Monitoreo (Zabbix).\n"))
check("--remove runs `quitar`, reads no value and sends none", rc == 0 and calls[0][0][-2:] == ["quitar", "zabbix"] and calls[0][1] == "" and "OK: Quitada" in out, (rc, out, calls))
print("\nall passed" if not fails else f"\n{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
