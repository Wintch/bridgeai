#!/usr/bin/env python3
"""Offline test of the always-on worker's `revista` type (workers/worker.py RevistaJob, workers/revista_job.py, apply.py --type revista;
WORKERS.md "The revista type").

No container, no network: a fake `docker` first in PATH (it runs the space reader and apply.py with this python3 on the mounted folders,
and plays `hub revista` from a fixture), a fake model server and a fake Telegram Bot API on 127.0.0.1.
Covers: config validation; the prompt comes from the person's jobs.json (their edit) with the "run hub revista" instruction replaced by
its output; NOTHING NEW still goes to the model (the job's prompt decides the one-line reply); the provider order and the fallback on a
500 (a provider without a key is never called; keys from the credential pool and from .env under another name); a model that hangs;
the 4096 split; the file saved without overwriting; the hub container has no keys and no network; no key, token or text in the events,
the state folder or the output; missing bot -> no model call, no send, failed no_bot; the skip rules (not moved, job still on, no job,
already sent today); the copied tables still match router.py and ops/lib/providers.py.
"""
import contextlib
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "workers"))
import revista_job  # noqa: E402
import worker  # noqa: E402

FAILS = []


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


NV_KEY = "fake-nvidia-pool-key-1111"
GM_KEY = "fake-gemini-env-key-2222"
TG_TOKEN = "4242:fake-bot-token-for-the-selftest"
PROMPT_MARK = "PERSONEDITEDPROMPT"
HUB_MARK = "HUBDIGESTITEM77"
ANSWER_MARK = "MAGAZINEANSWER55"
SECRETS = (NV_KEY, GM_KEY, TG_TOKEN, PROMPT_MARK, HUB_MARK, ANSWER_MARK)
PROMPT = ("Ejecuta en la terminal: hub revista . Si la salida dice NOTHING NEW y no tiene la sección COULD NOT BE FETCHED, contesta una "
          "sola línea breve diciendo que tus fuentes no tuvieron novedades. Si no, escribe la revista de la mañana. " + PROMPT_MARK)

FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, sys, time
ctl = os.environ["FAKE_CTL"]
a = sys.argv[1:]
with open(os.path.join(ctl, "docker.log"), "a") as f:
    f.write(json.dumps(a) + "\n")
if a[0] != "run":
    sys.exit(0)
VAL = {"--name", "--restart", "--network", "--memory", "--memory-swap", "--cpus", "--pids-limit", "--security-opt", "--cap-drop",
       "--cap-add", "--label", "-v", "-e", "--entrypoint", "--user"}
mounts, entry, i = {}, None, 1
while i < len(a) and a[i].startswith("-"):
    k = a[i]
    if "=" in k:
        i += 1; continue
    if k in VAL:
        v = a[i + 1]
        if k == "-v":
            p = v.split(":"); mounts[p[1]] = p[0]
        elif k == "--entrypoint":
            entry = v
        i += 2
    else:
        i += 1
image, rest = a[i], a[i + 1:]
def host(p):
    for dst in sorted(mounts, key=len, reverse=True):
        if p == dst or p.startswith(dst + "/"):
            return mounts[dst] + p[len(dst):]
    return p
if entry == "python3" and rest[:1] == ["-"]:       # the space reader, apply.py
    os.execvp("python3", ["python3", "-"] + [host(x) for x in rest[1:]])
if entry == "python3" and rest == ["/usr/local/bin/hub", "revista"]:
    b = open(os.path.join(ctl, "hub_behavior")).read().strip()
    if b == "hang":
        time.sleep(60)
    if b == "not_attached":
        sys.exit("hub: this stack is not attached to the collector yet (the operator runs ops/hub_attach.sh). Nothing was sent.")
    open(os.path.join(host("/workdir"), ".revista.json"), "w").write("{}")
    sys.stdout.write(open(os.path.join(ctl, "hub_out")).read())
    sys.exit(0)
sys.exit(125)
'''


class Fake(http.server.BaseHTTPRequestHandler):
    """The model servers (/p500, /ok, /slow, /empty under /v1/chat/completions) and the Bot API (/bot<token>/sendMessage)."""
    seen = []
    answer = ""
    tg_ok = True

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        Fake.seen.append({"path": self.path, "auth": self.headers.get("Authorization", ""), "body": body})
        if "/sendMessage" in self.path:
            code, out = (200, {"ok": True, "result": {}}) if Fake.tg_ok else (400, {"ok": False})
        elif self.path.startswith("/p500/"):
            code, out = 500, {"error": "boom"}
        elif self.path.startswith("/slow/"):
            time.sleep(3)
            code, out = 200, {"choices": [{"message": {"content": "late"}}]}
        elif self.path.startswith("/empty/"):
            code, out = 200, {"choices": [{"message": {"content": ""}}]}
        else:
            code, out = 200, {"choices": [{"message": {"role": "assistant", "content": "<think>x</think>" + Fake.answer}}]}
        data = json.dumps(out).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass


def model_calls(prefix=None):
    return [s for s in Fake.seen if "/chat/completions" in s["path"] and (prefix is None or s["path"].startswith(prefix))]


def tg_calls():
    return [s for s in Fake.seen if "/sendMessage" in s["path"]]


def main():
    tmp = tempfile.mkdtemp(prefix="revista-selftest-")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        run_all(tmp, base)
    finally:
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n".join(FAILS) if FAILS else "all worker revista checks passed")
    return 1 if FAILS else 0


def write_space(tmp, job_on=False, name="revista", moved=True, token=True):
    stack = os.path.join(tmp, "spaces", "novedades")
    persist, wd = os.path.join(stack, "persist"), os.path.join(stack, "workdir")
    os.makedirs(os.path.join(persist, "cron"), exist_ok=True)
    os.makedirs(wd, exist_ok=True)
    jobs = {"jobs": [{"id": "j0", "name": "otro", "prompt": "otra cosa: hub revista no", "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                      "enabled": True},
                     {"id": "j1", "name": name, "prompt": PROMPT, "schedule": {"kind": "cron", "expr": "30 7 * * *"}, "enabled": job_on,
                      "state": "scheduled" if job_on else "paused", "paused_at": None if job_on else "2026-11-27T08:00:00-03:00",
                      "deliver": "telegram", "no_agent": False}]}
    json.dump(jobs, open(os.path.join(persist, "cron", "jobs.json"), "w"))
    env = ["API_SERVER_ENABLED=true", f"GOOGLE_API_KEY={GM_KEY}", "TELEGRAM_ALLOWED_USERS=111, 222", "OTHER_SECRET=not-read"]
    if token:
        env.append(f"TELEGRAM_BOT_TOKEN={TG_TOKEN}")
    open(os.path.join(persist, ".env"), "w").write("\n".join(env) + "\n")
    json.dump({"credential_pool": {"custom:nvidia": [{"base_url": "https://elsewhere.example/v1", "api_key": "fake-wrong-host"}],
                                   "nvidia": [{"priority": 0, "api_key": NV_KEY, "auth_type": "api_key"}]}},
              open(os.path.join(persist, "auth.json"), "w"))
    wj = os.path.join(wd, ".worker-jobs")
    if moved:
        open(wj, "w").write("subs-nuevos\nrevista\n")
    elif os.path.exists(wj):
        os.unlink(wj)
    hub = os.path.join(tmp, "hubdata", "people", "novedades")
    os.makedirs(hub, exist_ok=True)
    open(os.path.join(hub, ".attached"), "w").close()
    return stack, persist, wd, hub


def run_all(tmp, base):
    # ---------------------------------------------------------------- tables match their sources
    env = dict(os.environ, GATEWAY_LOG=os.path.join(tmp, "gw.jsonl"))
    r = subprocess.run([sys.executable, "-I", "-c", "import sys, json; sys.path.insert(0, sys.argv[1]); import router; "
                        "print(json.dumps([router.CLOUD, router.OPENROUTER_PROVIDER, router.POOL_IDS, router.POOL_HOSTS]))", HERE],
                       capture_output=True, text=True, env=env, timeout=120)
    try:
        cloud, orp, pids, phosts = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        cloud = orp = pids = phosts = None
        print(r.stderr[-2000:])
    ok(cloud == [list(c) for c in revista_job.CLOUD], "revista_job.CLOUD is router.py's CLOUD (same order, URLs, models, key variables)")
    ok(orp == revista_job.OPENROUTER_PROVIDER, "OpenRouter privacy preferences are router.py's")
    ok(pids == revista_job.POOL_IDS and phosts == revista_job.POOL_HOSTS, "credential pool ids and hosts are router.py's")
    sys.path.insert(0, os.path.join(HERE, "ops", "lib"))
    import providers
    env_of = {d["env"][0]: d["env"] for d in providers.PROVIDERS.values()}
    ok(all(revista_job.KEY_NAMES[v] == env_of.get(v, [v]) for v in revista_job.KEY_NAMES), "key variable names match ops/lib/providers.py")
    ok({c[3] for c in revista_job.CLOUD} <= set(revista_job.KEY_NAMES), "every CLOUD key variable has its names")

    # ---------------------------------------------------------------- pure helpers
    parts = revista_job.split_text("a" * 9000)
    ok(len(parts) == 3 and "".join(parts) == "a" * 9000 and all(revista_job.u16(p) <= 4096 for p in parts), "split: hard cut at 4096")
    txt = ("línea de la revista 🙂 con emoji\n" * 400) + "\n\n" + ("otra sección\n" * 300)
    parts = revista_job.split_text(txt)
    ok("".join(parts) == txt and all(revista_job.u16(p) <= 4096 for p in parts) and all(p.endswith("\n") for p in parts[:-1]),
       f"split: at line ends, UTF-16 units counted (emoji = 2), lossless ({len(parts)} pieces)")
    ok(revista_job.split_text("short") == ["short"], "split: a short text is one piece")
    um = revista_job.user_message(PROMPT, "DIGEST\n")
    ok(um.startswith("(`hub revista` was already run for you") and "Ejecuta en la terminal" not in um and "Si la salida dice NOTHING NEW" in um
       and um.rstrip().endswith("Here is the output of `hub revista`:\nDIGEST"), "user message: the run instruction is replaced, the output follows")
    um2 = revista_job.user_message("Write my magazine.", "D")
    ok(um2.startswith("(`hub revista` was already run") and "Write my magazine." in um2 and "output of `hub revista`" in um2,
       "user message: a prompt that does not name the command gets the note in front")
    ok(revista_job.chats_of("111, 222,x, -100123") == ["111", "222", "-100123"], "allowed users: numeric chat ids only")

    # model order, fallback, timeout (unit level)
    saved_cloud = revista_job.CLOUD
    revista_job.CLOUD = [("A", base + "/slow/v1", "m-a", "NVIDIA_API_KEY"), ("B", base + "/empty/v1", "m-b", "GEMINI_API_KEY"),
                         ("C", base + "/ok/v1", "m-c", "OPENROUTER_API_KEY")]
    Fake.answer = "fine"
    Fake.seen.clear()
    text, info = revista_job.call_model({"NVIDIA_API_KEY": "k1", "GEMINI_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}, "s", "u",
                                        time.time() + 60, per_call_s=1)
    ok(text == "fine" and info["codes"] == ["timeout", "empty", "200"] and info["tries"] == 3,
       f"model: a hung provider times out, an empty answer falls through, the next answers ({info['codes']})")
    ok(model_calls("/ok/")[0]["body"].get("provider") is None, "model: no OpenRouter preferences on a non-OpenRouter URL")
    text, info = revista_job.call_model({"GEMINI_API_KEY": "k2"}, "s", "u", time.time() + 60, cloud_order=["C", "B"])
    ok(text is None and info["tries"] == 1 and info["codes"] == ["empty"], "model: only providers with a key are tried; none left = None")
    revista_job.CLOUD = saved_cloud

    # ---------------------------------------------------------------- the worker, end to end
    shims, ctl = os.path.join(tmp, "shims"), os.path.join(tmp, "ctl")
    os.makedirs(shims)
    os.makedirs(ctl)
    open(os.path.join(shims, "docker"), "w").write(FAKE_DOCKER)
    os.chmod(os.path.join(shims, "docker"), 0o755)
    os.environ["PATH"] = shims + os.pathsep + os.environ.get("PATH", "")
    os.environ["FAKE_CTL"] = ctl
    stack, persist, wd, hub = write_space(tmp)
    open(os.path.join(ctl, "hub_behavior"), "w").write("ok")
    open(os.path.join(ctl, "hub_out"), "w").write(f"REVISTA DIGEST.\n== BY SOURCE ==\n[x1] {HUB_MARK} item\n== END ==\n")
    state = os.path.join(tmp, "state")
    revista_job.CLOUD = [("A", base + "/p500/v1", "m-a", "NVIDIA_API_KEY"), ("B", base + "/nokey/v1", "m-b", "TOKENHARBOR_API_KEY"),
                         ("C", base + "/ok/v1", "m-c", "GEMINI_API_KEY")]

    def config(apply="direct", **job):
        jc = {"local_hub": hub, "bot_api": base}
        jc.update(job)
        jc = {k: v for k, v in jc.items() if v is not None}
        cfg = {"image": "aibridge-hermes-agent:latest", "apply": apply, "state_dir": state,
               "types": {"revista": {"schedule": "*-*-* 07:30:00", "timeout_s": 60}},
               "people": {"novedades": {"local_workdir": wd, "jobs": {"revista": jc}}}}
        p = os.path.join(tmp, "workers.json")
        json.dump(cfg, open(p, "w"))
        return worker.load_config(p)

    def events():
        try:
            return [json.loads(x) for x in open(os.path.join(state, "events.jsonl"))]
        except OSError:
            return []

    def run(cfg):
        n = len(events())
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = worker.cmd_run(cfg, "revista", None)
        return rc, events()[n:], out.getvalue() + err.getvalue()

    def reset_day():
        m = os.path.join(state, "novedades", "revista", "meta.json")
        if os.path.exists(m):
            d = json.load(open(m))
            d.pop("last_sent_day", None)
            json.dump(d, open(m, "w"))

    def docker_runs(kind):
        rows = [json.loads(x) for x in open(os.path.join(ctl, "docker.log"))] if os.path.exists(os.path.join(ctl, "docker.log")) else []
        if kind == "hub":
            return [a for a in rows if a[0] == "run" and a[-2:] == ["/usr/local/bin/hub", "revista"]]
        return [a for a in rows if a[0] == "run" and "-" in a[a.index("--entrypoint") + 2:][:2]]

    # validation
    def errs(mut):
        c = {"types": {"revista": {"schedule": "*-*-* 07:30:00"}},
             "people": {"novedades": {"local_workdir": wd, "jobs": {"revista": {"local_hub": hub, "bot_api": "http://bot-api-host:8081"}}}}}
        mut(c)
        return worker.validate(c)
    ok(errs(lambda c: None) == [], "config: a local person with local_hub and bot_api is valid")
    def remote(c):
        c["people"]["novedades"].pop("local_workdir")
        c["people"]["novedades"]["remote_workdir"] = "a/b"
        c["host"] = "aibridge@docker-host"
    ok(any("local data mode only" in e for e in errs(remote)), "config: revista needs local_workdir")
    ok(any("local_hub" in e for e in errs(lambda c: c["people"]["novedades"]["jobs"]["revista"].pop("local_hub"))), "config: local_hub is required")
    ok(any("bot_api" in e for e in errs(lambda c: c["people"]["novedades"]["jobs"]["revista"].update(bot_api="http://h:8081/bot123:abc"))),
       "config: bot_api is a base URL only (no path, no token)")
    ok(any("unknown key" in e for e in errs(lambda c: c["people"]["novedades"]["jobs"]["revista"].update(token="x"))), "config: unknown keys refused")
    ok(any("cloud_order" in e for e in errs(lambda c: c["people"]["novedades"]["jobs"]["revista"].update(cloud_order="A"))), "config: cloud_order is a list")

    # 1. the normal morning: 500 then the next provider, 9000 characters to two people, the file saved beside an existing one
    day = time.strftime("%Y-%m-%d")
    os.makedirs(os.path.join(wd, "revista"))
    open(os.path.join(wd, "revista", f"{day}.md"), "w").write("MINE\n")
    Fake.answer = (ANSWER_MARK + " " + "noticia breve con enlace https://example.org/x\n" * 200)[:9000]
    Fake.seen.clear()
    rc, evs, out = run(config())
    subj = [e["subject"] for e in evs]
    ok(rc == 0 and subj == ["ev.worker.revista.started", "ev.worker.revista.pushed", "ev.worker.revista.done"], f"normal run: started, pushed, done ({subj})")
    calls = model_calls()
    ok([c["path"].split("/")[1] for c in calls] == ["p500", "ok"], "model: the first provider's 500 falls to the next with a key (B has no key: never called)")
    ok(calls[0]["auth"] == f"Bearer {NV_KEY}" and calls[1]["auth"] == f"Bearer {GM_KEY}",
       "keys: NVIDIA from the credential pool (an entry for another host ignored), Gemini from .env's GOOGLE_API_KEY")
    msgs = calls[1]["body"]["messages"]
    ok(msgs[0]["role"] == "system" and "scheduled run" in msgs[0]["content"] and "`hub revista` was already run" in msgs[0]["content"],
       "model: the system message says it is the scheduled magazine run")
    u = msgs[1]["content"]
    ok(PROMPT_MARK in u and HUB_MARK in u and "Here is the output of `hub revista`" in u and "Ejecuta en la terminal" not in u,
       "model: the person's current prompt from jobs.json, the run instruction replaced by the hub output")
    ok(calls[1]["body"]["model"] == "m-c" and calls[1]["body"].get("stream") is False, "model: the provider's model, not streamed")
    tgs = tg_calls()
    ok(len(tgs) == 6 and [t["body"]["chat_id"] for t in tgs] == ["111"] * 3 + ["222"] * 3, f"telegram: 3 pieces to each of the 2 allowed users ({len(tgs)})")
    ok(all(t["path"] == f"/bot{TG_TOKEN}/sendMessage" for t in tgs), "telegram: the stack's own bot token, through bot_api")
    ok(all(revista_job.u16(t["body"]["text"]) <= 4096 and t["body"]["link_preview_options"] == {"is_disabled": True}
           and "parse_mode" not in t["body"] for t in tgs), "telegram: pieces of at most 4096, plain text, link previews off")
    joined = "".join(t["body"]["text"] for t in tgs[:3])
    ok(joined.startswith("🕖 Programado · "), "telegram: the first line says a schedule sent it (NOTICES.md)")
    ok(joined.split("\n\n", 1)[1].replace("\n", "") == Fake.answer.strip().replace("\n", ""), "telegram: the whole answer, in order")
    ok(open(os.path.join(wd, "revista", f"{day}.md")).read() == "MINE\n", "file: an existing file of the day is never replaced")
    ok(open(os.path.join(wd, "revista", f"{day}-2.md")).read() == Fake.answer.strip() + "\n", "file: the magazine is saved as <day>-2.md")
    ok(os.path.exists(os.path.join(wd, ".revista.json")), "hub revista kept its window in the person's workdir")
    h = docker_runs("hub")[-1]
    vols = [h[i + 1] for i, x in enumerate(h) if x == "-v"]
    ok(h[h.index("--network") + 1] == "none" and "-e" not in h and "--env-file" not in h and vols == [f"{hub}:/hub:ro", f"{wd}:/workdir"],
       f"hub container: no network, no env, only the hub (read-only) and the workdir ({vols})")
    ok(not any(persist in x for x in h), "hub container: the person's persist (keys) is not mounted")
    done = evs[-1]["data"]
    ok(done.get("tries") == 2 and done.get("sent") == 6 and done.get("pieces") == 3 and done.get("users") == 2 and done.get("send_failed") == 0
       and done.get("answer_chars") == len(Fake.answer.strip()), f"done event: counts ({done})")

    def leaks(text):
        return [s for s in SECRETS if s in text]
    blob = out
    for d, _, files in os.walk(state):
        for f in files:
            blob += open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
    ok(leaks(blob) == [], f"no key, token, prompt, digest or answer in the events, the state folder or the output ({leaks(blob)})")

    # 2. the same day again: already sent
    Fake.seen.clear()
    rc, evs, _ = run(config())
    ok(rc == 0 and evs[-1]["data"].get("reason") == "already_sent" and not model_calls() and not tg_calls(), "a second run the same day: skipped, nothing sent")

    # 3. NOTHING NEW still goes to the model: the job's prompt decides the one-line reply
    reset_day()
    open(os.path.join(ctl, "hub_out"), "w").write("REVISTA DIGEST.\nNOTHING NEW in the followed sources since the window began.\n== END ==\n")
    Fake.answer = "Tus fuentes no tuvieron novedades."
    Fake.seen.clear()
    rc, evs, _ = run(config())
    calls = model_calls("/ok/")
    ok(rc == 0 and len(calls) == 1 and "NOTHING NEW" in calls[0]["body"]["messages"][1]["content"], "NOTHING NEW: the model is still asked")
    ok(len(tg_calls()) == 2 and all(t["body"]["text"].startswith("🕖 Programado · ") and t["body"]["text"].endswith(Fake.answer)
                                    for t in tg_calls()), "NOTHING NEW: its one line reaches both people, marked as scheduled")
    ok(os.path.exists(os.path.join(wd, "revista", f"{day}-3.md")), "NOTHING NEW: saved too, under the next free name")

    # 4. the hub is not attached: its own message goes to the model with the exit code
    reset_day()
    open(os.path.join(ctl, "hub_behavior"), "w").write("not_attached")
    Fake.seen.clear()
    rc, evs, _ = run(config())
    u = model_calls("/ok/")[0]["body"]["messages"][1]["content"] if model_calls("/ok/") else ""
    ok(rc == 0 and "not attached" in u and "exit code 1" in u, "hub exit 1 with its plain message: the model is told, so the person is")
    open(os.path.join(ctl, "hub_behavior"), "w").write("ok")

    # 5. no bot: no model call, no send, failed no_bot
    for what, cfg in (("no bot_api", config(bot_api=None)), ("no token", None)):
        reset_day()
        if cfg is None:
            write_space(tmp, token=False)
            cfg = config()
        Fake.seen.clear()
        rc, evs, _ = run(cfg)
        e = evs[-1]
        ok(rc == 1 and e["subject"] == "ev.worker.revista.failed" and e["data"].get("reason") == "no_bot" and not Fake.seen,
           f"{what}: failed reason=no_bot, the model is not called, nothing is sent")
    write_space(tmp)

    # 6. the skip rules
    for what, kw, reason in (("not in .worker-jobs", {"moved": False}, "not_moved"), ("still on in the stack", {"job_on": True}, "job_active"),
                             ("job removed", {"name": "otro2"}, "no_job")):
        reset_day()
        write_space(tmp, **kw)
        Fake.seen.clear()
        n_hub = len(docker_runs("hub"))
        rc, evs, _ = run(config())
        ok(rc == 0 and evs[-1]["data"].get("reason") == reason and not Fake.seen and len(docker_runs("hub")) == n_hub,
           f"{what}: skipped {reason}, no hub run, no model, no send")
    write_space(tmp)

    # 7. every provider fails: failed model, nothing sent, nothing saved
    reset_day()
    revista_job.CLOUD = [("A", base + "/p500/v1", "m-a", "NVIDIA_API_KEY")]
    before = sorted(os.listdir(os.path.join(wd, "revista")))
    Fake.seen.clear()
    rc, evs, _ = run(config())
    ok(rc == 1 and evs[-1]["data"].get("reason") == "model" and evs[-1]["data"].get("last_code") == "http_500" and not tg_calls()
       and sorted(os.listdir(os.path.join(wd, "revista"))) == before, "all providers fail: failed model, no send, no file")
    revista_job.CLOUD = [("A", base + "/p500/v1", "m-a", "NVIDIA_API_KEY"), ("C", base + "/ok/v1", "m-c", "GEMINI_API_KEY")]

    # 8. Telegram refuses: failed send, the magazine is still saved for the bot, a later run may try again
    reset_day()
    Fake.tg_ok = False
    Fake.seen.clear()
    rc, evs, _ = run(config())
    ok(rc == 1 and evs[-1]["data"].get("reason") == "send" and evs[-1]["data"].get("sent") == 0 and len(tg_calls()) == 2,
       "telegram refuses: failed send (one try per person, the rest not sent)")
    Fake.tg_ok = True
    Fake.seen.clear()
    rc, evs, _ = run(config())
    ok(rc == 0 and len(tg_calls()) == 2, "after a failed send the next run is not skipped as already sent")

    # 9. apply: docker -> the reader and apply.py run in one-shot containers (root, no network, persist read-only)
    reset_day()
    open(os.path.join(ctl, "docker.log"), "w").close()
    Fake.seen.clear()
    rc, evs, _ = run(config(apply="docker"))
    rd = [a for a in docker_runs("py") if f"{persist}:/p:ro" in a]
    ok(rc == 0 and len(rd) == 1 and rd[0][rd[0].index("--network") + 1] == "none" and "-i" in rd[0] and f"{wd}:/w:ro" in rd[0],
       "apply docker: the space is read by a one-shot container (no network, persist and workdir read-only)")
    ap = [a for a in docker_runs("py") if any(x.endswith(":/inbox") for x in a)]
    ok(len(ap) == 1 and "--type" in ap[0] and ap[0][ap[0].index("--type") + 1] == "revista", "apply docker: the file goes in through apply.py --type revista")

    # 10. the hub hangs: the run's deadline kills it
    reset_day()
    open(os.path.join(ctl, "hub_behavior"), "w").write("hang")
    cfg = config()
    cfg["types"]["revista"]["timeout_s"] = 12
    Fake.seen.clear()
    t0 = time.time()
    rc, evs, _ = run(cfg)
    ok(rc == 1 and evs[-1]["data"].get("reason") == "hub_timeout" and time.time() - t0 < 40 and not Fake.seen,
       "a hung hub container: failed hub_timeout within the deadline, no model call")
    ok(any(a[0] == "kill" for a in [json.loads(x) for x in open(os.path.join(ctl, "docker.log"))]), "a hung hub container is killed")


if __name__ == "__main__":
    sys.exit(main())
