#!/usr/bin/env python3
"""archivo.py against a fake history and a fake /workdir. No network: python3 archivo_selftest.py"""
import io, os, sqlite3, sys, tempfile, contextlib
tmp = tempfile.mkdtemp()
os.environ["ARCHIVO_DB"] = os.path.join(tmp, "state.db")
os.environ["ARCHIVO_ROOT"] = os.path.join(tmp, "workdir")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archivo as a

fails = []
def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails.append(name)

def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = a.main(list(argv))
    return code, buf.getvalue()

d = os.path.join(tmp, "workdir", "descargas")
os.makedirs(d)
alive = os.path.join(d, "Johnny Mnemonic - Trailer (Upscaled 4K) [qWal76WdV7U].mp4")
open(alive, "wb").write(b"x" * 2048)
open(os.path.join(d, "synced_pip.mp4"), "wb").write(b"y")
os.makedirs(os.path.join(tmp, "workdir", "venvs", "v"))
open(os.path.join(tmp, "workdir", "venvs", "v", "Johnny.py"), "w").write("skip me")
db = sqlite3.connect(os.environ["ARCHIVO_DB"])
db.execute("create table messages (role text, content text, timestamp real)")
msgs = [("assistant", f"MEDIA:{alive}", 1793000000.0),
        ("assistant", "MEDIA:/tmp/trailers/lowq/Dark City (1998) Official Trailer [abcdefghijk].mp4", 1792990000.0),
        ("assistant", "MEDIA:/root/.hermes/cache/audio/tts_20261105_1.ogg\n\n[[audio_as_voice]]", 1793000500.0),
        ("user", "MEDIA:/tmp/not-from-the-assistant.mp4", 1793000600.0)]
db.executemany("insert into messages values (?,?,?)", msgs); db.commit()

code, out = run("buscar", "jonny", "mnemonic")          # typo + lower case
check("typo and case still find an existing file", "EXISTE" in out and "Johnny Mnemonic - Trailer" in out and "venvs" not in out)
code, out = run("buscar", "dark", "city")
check("a delivered file that is gone is PERDIDO, says why and gives the source link", "PERDIDO" in out and "se pierde al recrear" in out and "https://youtu.be/abcdefghijk" in out)
check("never says nothing when a PERDIDO line exists", "Nunca digas que no hay nada" in out)
code, out = run("buscar", "tts")
check("voice replies are left out unless asked", "PERDIDO" not in out)
code, out = run("buscar", "tts", "--audio")
check("--audio includes them", "tts_20261105_1.ogg" in out)
code, out = run("buscar", "not-from-the-assistant")
check("only what the assistant sent counts as delivered", "SIN COINCIDENCIA" in out)
code, out = run("buscar", "mnemonik", "trailr")
check("close spellings of both words match", "EXISTE" in out)
code, out = run("buscar", "blade", "runner")
check("no match says so and lists nothing invented", "SIN COINCIDENCIA" in out and "EXISTE" not in out)
code, out = run("lista", "5")
check("lista shows newest first, without voice", out.splitlines()[0].startswith(a.when(1793000000.0)) and "tts_" not in out)
code, out = run("borrar", alive)
check("borrar without a reason is refused and deletes nothing", code == 2 and os.path.exists(alive))
code, out = run("borrar", "/etc/passwd", "--motivo", "x")
check("borrar refuses paths outside the workdir", code == 2)
code, out = run("borrar", alive, "--motivo", "disk at 90 percent")
check("borrar deletes and writes a tombstone", code == 0 and not os.path.exists(alive) and os.path.exists(a.TOMB))
code, out = run("buscar", "johnny", "mnemonic")
check("after borrar the search reports PERDIDO and BORRADO with the reason", "BORRADO" in out and "disk at 90 percent" in out and "PERDIDO" in out)
print("\n".join(fails) or "archivo_selftest: all ok")
sys.exit(1 if fails else 0)
