# Replaces hernik's disabled davinci-resolve MCP entry with two enabled ones (community `davinci`, vendor `davinci-native`).
# Run INSIDE the stack container (docker cp it in, then `python3 edit_hernik_mcp_config.py`); `--dry` writes config.yaml.dry instead.
# Backs up config.yaml first. The new entries are read at the next Hermes start or /new.
import re, shutil, sys, time
path = sys.argv[1] if len(sys.argv) > 1 else "/root/.hermes/config.yaml"
s = open(path).read()
new = """  davinci-resolve:
    command: ssh
    args:
      - -o
      - ConnectTimeout=3
      - -o
      - BatchMode=yes
      - resolve-host-mcp
      - davinci
    connect_timeout: 120.0
    # community davinci-resolve-mcp (37 tools) against Resolve in a private virtual display; renders take a while (2026-11-04)
    timeout: 300.0
    enabled: true
  davinci-native:
    command: ssh
    args:
      - -o
      - ConnectTimeout=3
      - -o
      - BatchMode=yes
      - resolve-host-mcp
      - davinci-native
    connect_timeout: 120.0
    # vendor ResolveMCP (13 tools, run_script_unsafe filtered out on the server) against the same Resolve (2026-11-04)
    timeout: 120.0
    enabled: true
"""
m = re.search(r"^  davinci-resolve:\n(?:(?:    .*|\s*)\n)*", s, re.M)
if not m or "davinci-native:" in s:
    sys.exit("nothing to do or unexpected layout: no change made")
if path.endswith("config.yaml") and "--dry" not in sys.argv:
    shutil.copy(path, path + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
out = s[:m.start()] + new + s[m.end():]
open(path if "--dry" not in sys.argv else path + ".dry", "w").write(out)
print("ok", "(dry run)" if "--dry" in sys.argv else "")
