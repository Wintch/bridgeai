#!/usr/bin/env python3
"""steam-compat-tool.py CONFIG_VDF APPID TOOL: forces a compatibility tool (e.g. proton_experimental) for one game in Steam's config.vdf
(InstallConfigStore/Software/Valve/Steam/CompatToolMapping), what "Properties -> Compatibility -> Force" does. Steam must be CLOSED (it rewrites
the file on exit). TOOL "" removes the mapping. Backup first; prints old and new. Forcing Proton on a game with a Linux build makes Steam download
the Windows build (a full download)."""
import os, re, shutil, sys, time

path, appid, tool = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path, encoding="utf-8", errors="surrogateescape").read()


def tokens(s):
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            yield ("str", s[i + 1:j], i, j + 1); i = j + 1
        elif c in "{}":
            yield (c, c, i, i + 1); i += 1
        else:
            i += 1


def block(s, keys):
    stack, last = [], None
    for kind, val, a, b in tokens(s):
        if kind == "str":
            last = val
        elif kind == "{":
            stack.append((last or "").lower()); last = None
            if len(stack) >= len(keys) and stack[-len(keys):] == [k.lower() for k in keys]:
                depth = 0
                for k2, v2, a2, b2 in tokens(s[a:]):
                    if k2 == "{": depth += 1
                    elif k2 == "}":
                        depth -= 1
                        if depth == 0:
                            return a, a + a2
        elif kind == "}":
            stack and stack.pop(); last = None
    return None


steam = block(src, ["Software", "Valve", "Steam"])
if not steam:
    sys.exit("no Software/Valve/Steam block")
ind = "\t\t\t\t"                          # children of the Steam block
entry = (f'{ind}\t"{appid}"\n{ind}\t{{\n{ind}\t\t"name"\t\t"{tool}"\n{ind}\t\t"config"\t\t""\n{ind}\t\t"priority"\t\t"250"\n{ind}\t}}\n') if tool else ""
ctm = block(src[steam[0]:steam[1] + 1], ["CompatToolMapping"])
old = None
if ctm:
    a, b = steam[0] + ctm[0], steam[0] + ctm[1]
    body = src[a:b + 1]
    cur = block(body, [appid])
    if cur:
        seg = body[cur[0]:cur[1] + 1]
        m = re.search(r'"name"\s*"([^"]*)"', seg); old = m.group(1) if m else ""
        start = body.rfind(f'"{appid}"', 0, cur[0]); start = body.rfind("\n", 0, start) + 1
        body = body[:start] + body[cur[1] + 2:]
    if tool:
        ls = body.rfind("\n", 0, len(body) - 1) + 1          # the line of the block's closing brace
        body = body[:ls] + entry + body[ls:]
    new = src[:a] + body + src[b + 1:]
else:
    if not tool:
        print("nothing to remove"); sys.exit(0)
    ls = src.rfind("\n", 0, steam[1]) + 1                   # the line of the Steam block's closing brace
    new = src[:ls] + f'{ind}"CompatToolMapping"\n{ind}{{\n{entry}{ind}}}\n' + src[ls:]
bak = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
shutil.copy2(path, bak)
open(path + ".tmp", "w", encoding="utf-8", errors="surrogateescape").write(new)
shutil.copystat(path, path + ".tmp"); os.replace(path + ".tmp", path)
print(f"appid {appid}: compat tool {old!r} -> {tool!r} (backup {bak})")
