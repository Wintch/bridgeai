#!/usr/bin/env python3
"""Self-test for patches/text_tool_call_retry.py on a stand-in of Hermes's agent/turn_final_response.py (its three anchors,
verbatim). The real file is checked at image build time (the patch aborts unless each anchor matches once).
Run: python3 -I text_tool_call_retry_selftest.py
"""
import os
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


STANDIN = '''
from dataclasses import dataclass
_DROPPED_TOOLCALL_NUDGE_CONTENT = "DROPPED"


def append_message(messages, msg):
    messages.append(msg)


@dataclass
class FinalResponseVerdict:
    action: str


def run(agent, assistant_message, finish_reason, final_response, messages):
    final_msg = {"role": "assistant", "content": final_response}

    def _verdict(action):
        return action
    if (
        finish_reason == "tool_calls"
        and not assistant_message.tool_calls
        and getattr(agent, "_dropped_toolcall_retries", 0) < 3
    ):
        agent._dropped_toolcall_retries = getattr(agent, "_dropped_toolcall_retries", 0) + 1
        final_msg["_dropped_toolcall_nudge"] = True
        append_message(messages, final_msg)
        append_message(messages, {
            "role": "user",
            "content": _DROPPED_TOOLCALL_NUDGE_CONTENT,
            "_dropped_toolcall_nudge": True,
        })
        return _verdict("continue")
    agent._dropped_toolcall_retries = 0
    return _verdict("return")
'''

d = tempfile.mkdtemp()
p = os.path.join(d, "turn_final_response.py")
open(p, "w").write(STANDIN)
patch = os.path.join(HERE, "patches", "text_tool_call_retry.py")
r1 = subprocess.run([sys.executable, patch, p], capture_output=True, text=True)
r2 = subprocess.run([sys.executable, patch, p], capture_output=True, text=True)
check("the patch applies to the stand-in", r1.returncode == 0 and "patched" in r1.stdout, r1.stdout + r1.stderr)
check("a second run is a no-op", r2.returncode == 0 and "already patched" in r2.stdout, r2.stdout + r2.stderr)
bad = os.path.join(d, "other.py")
open(bad, "w").write("def run():\n    pass\n")
r3 = subprocess.run([sys.executable, patch, bad], capture_output=True, text=True)
check("a file without the anchors aborts the build", r3.returncode != 0 and "patch failed" in (r3.stdout + r3.stderr), r3.stdout + r3.stderr)

m = types.ModuleType("tfr")
exec(compile(open(p).read(), p, "exec"), m.__dict__)


class Agent:
    def __init__(self, names=("terminal", "skill_view", "text_to_speech", "web_search")):
        self.valid_tool_names = set(names)


class Msg:
    tool_calls = None


# The reply hernik got (prompt shortened).
LEAK = ('Este generará video real con movimiento y sonido. Tarda unos 3-7 minutos; lo lanzo en segundo plano y te aviso '
        'cuando termine.\n\n[\n  {\n    "name": "terminal",\n    "arguments": {\n      "command": "gateway makevideo --secs 3 '
        '-- \\"a lighthouse at sunset\\" /workdir/descargas/clip.mp4",\n      "background": true,\n      "notify": true\n'
        '    }\n  }\n]')
a = Agent()
check("the real leaked reply names terminal", m._text_tool_call(LEAK, a), "terminal")
shapes = {
    "single object": '{"name": "web_search", "arguments": {"query": "x"}}',
    "arguments as a JSON string": 'ok: {"name": "terminal", "arguments": "{\\"command\\": \\"ls\\"}"}',
    "function wrapper": '[{"type": "function", "function": {"name": "skill_view", "arguments": {"name": "video-generation"}}}]',
    "tool/parameters keys inside a tag": '<tool_call>{"tool": "text_to_speech", "parameters": {"text": "hola"}}</tool_call>',
    "after unrelated braces and a broken object": 'set {a} and {"x": 1 then {"name": "terminal", "args": {"command": "ls"}}',
}
for what, text in shapes.items():
    check(f"detected: {what}", m._text_tool_call(text, a) is not None, text)
negatives = {
    "plain prose": "Listo, te aviso cuando termine.",
    "inside a code block (an example the person asked for)": 'Así se ve:\n```json\n{"name": "terminal", "arguments": {"command": "ls"}}\n```',
    "an unknown tool name": '{"name": "process_manage", "arguments": {"action": "list"}}',
    "a name with no arguments": '{"name": "terminal", "status": "ok"}',
    "ordinary JSON data": '{"name": "Juan", "age": 30}',
    "not a string": None,
}
for what, text in negatives.items():
    check(f"not detected: {what}", m._text_tool_call(text, a) is None, text)
check("an agent with no tool list never matches", m._text_tool_call(LEAK, Agent(())) is None)
check("a huge reply is cut before scanning (no slow parse)", m._text_tool_call("{" * 200000, a) is None)

msgs, ag = [], Agent()
check("a leaked call continues the turn", m.run(ag, Msg(), "stop", LEAK, msgs), "continue")
check("both halves of the retry pair are ephemeral scaffolding",
      [x.get("_dropped_toolcall_nudge") for x in msgs] == [True, True], msgs)
nudge = msgs[-1]["content"]
check("the nudge names the tool, says nothing ran, and allows a mere example",
      all(w in nudge for w in ("`terminal`", "did NOT run", "nothing was started", "example")), nudge)
for _ in range(2):
    m.run(ag, Msg(), "stop", LEAK, msgs)
check("at most 3 retries in a row, then the reply goes out", m.run(ag, Msg(), "stop", LEAK, msgs), "return")
msgs = []
check("an ordinary answer ends the turn", m.run(Agent(), Msg(), "stop", "Listo.", msgs) == "return" and msgs == [])
msgs = []
check("finish_reason=tool_calls with no call keeps Hermes's own nudge",
      m.run(Agent(), Msg(), "tool_calls", "", msgs) == "continue" and msgs[-1]["content"] == "DROPPED", msgs)

print("text_tool_call_retry selftest: " + ("FAILED: " + "; ".join(fails) if fails else "all ok"))
sys.exit(1 if fails else 0)
