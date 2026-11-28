#!/usr/bin/env python3
"""set_launch.py LOCALCONFIG APPID 'OPTIONS': sets apps/<APPID>/LaunchOptions in Steam's userdata localconfig.vdf (Steam must be closed).
Keeps everything else byte for byte; writes LOCALCONFIG.bak-<time> first; prints the old and the new value."""
import os, re, shutil, sys, time

path, appid, opts = sys.argv[1], sys.argv[2], sys.argv[3]
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

def find_block(s, keys):
    """(open, close) positions of the block reached by the key path, case-insensitive."""
    stack, last_str = [], None
    for kind, val, a, b in tokens(s):
        if kind == "str":
            last_str = val
        elif kind == "{":
            stack.append((last_str or "").lower()); last_str = None
            if [k.lower() for k in keys] == stack[-len(keys):] and len(stack) >= len(keys):
                depth, start = 0, a
                for k2, v2, a2, b2 in tokens(s[a:]):
                    if k2 == "{": depth += 1
                    elif k2 == "}":
                        depth -= 1
                        if depth == 0:
                            return start, a + a2
        elif kind == "}":
            stack.pop() if stack else None; last_str = None
    return None

apps = find_block(src, ["Software", "Valve", "Steam", "apps"])
if not apps:
    sys.exit("no Software/Valve/Steam/apps block")
blk = find_block(src[apps[0]:apps[1] + 1], [appid])
esc = opts.replace("\\", "\\\\").replace('"', '\\"')
if blk:
    a, b = apps[0] + blk[0], apps[0] + blk[1]
    body = src[a:b + 1]
    m = re.search(r'(\n(\s*)"LaunchOptions"\s*")((?:[^"\\]|\\.)*)(")', body)
    old = m.group(3) if m else None
    if m:
        body = body[:m.start(3)] + esc + body[m.end(3):]
    else:
        ind = re.search(r"\n(\s*)\"", body)
        indent = ind.group(1) if ind else "\t\t\t\t\t\t"
        body = body[:-1].rstrip("\t") + f'{indent}"LaunchOptions"\t\t"{esc}"\n' + body[len(body[:-1].rstrip("\t")):]
    new = src[:a] + body + src[b + 1:]
else:
    old = None
    close = apps[1]
    line_start = src.rfind("\n", 0, close) + 1
    indent = src[line_start:close]
    new = src[:close] + f'\t"{appid}"\n{indent}\t{{\n{indent}\t\t"LaunchOptions"\t\t"{esc}"\n{indent}\t}}\n{indent}' + src[close:]
bak = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
shutil.copy2(path, bak)
tmp = path + ".tmp"
open(tmp, "w", encoding="utf-8", errors="surrogateescape").write(new)
shutil.copystat(path, tmp); os.replace(tmp, path)
print(f"old={old!r} new={opts!r} backup={bak}")
