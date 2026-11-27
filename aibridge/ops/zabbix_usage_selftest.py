#!/usr/bin/env python3
"""Offline: provision.py gpu-usage-host / heat-host against a fake Zabbix API. An existing host keeps its other templates and macros (only
this template's macro is created or updated: host.update with "macros" would replace them all), a new host gets the template, tags and
macro, and the import also loads value maps and discovery rules. Run: python3 -I ops/zabbix_usage_selftest.py"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("provision", os.path.join(HERE, "zabbix", "provision.py"))
pv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pv)
fails = []


def check(label, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + label + ("" if ok else f"   {detail}"))
    if not ok:
        fails.append(label)


class Fake:
    def __init__(self, host=None, macro=None):
        self.calls, self.host, self.macro = [], host, macro

    def api(self, method, params):
        self.calls.append((method, params))
        if method == "host.get":
            return [self.host] if self.host else []
        if method == "template.get":
            return [{"templateid": "T-" + params["filter"]["host"]}]
        if method == "usergroup.get":
            return [{"usrgrpid": "UG", "hostgroup_rights": [{"id": "G0", "permission": "2"}]}]
        if method == "hostgroup.get":
            return [{"groupid": "G1"}]
        if method == "usermacro.get":
            return [self.macro] if self.macro else []
        return {}


def run(fake, fn, *a):
    pv.api = fake.api
    pv.one = lambda m, p: (fake.api(m, p) or [None])[0]
    pv.require_super_admin = lambda: None
    fn(*a)
    return fake.calls


# an existing host that already carries the heat template and its macro
f = Fake(host={"hostid": "H1", "description": "", "parentTemplates": [{"templateid": "T-GPU host heat"}], "tags": [{"tag": "x", "value": "y"}]})
calls = run(f, pv.usage_host, "bridgeai-aishur", "192.168.0.9", "aishur", True)
upd = [p for m, p in calls if m == "host.update"]
check("existing host: host.update never carries 'macros' (it would drop the heat macro)", upd and all("macros" not in p for p in upd), upd)
check("existing host: both templates kept", upd and {t["templateid"] for t in upd[0]["templates"]} == {"T-GPU host heat", "T-GPU host usage"}, upd)
check("existing host: other tags kept, project/unit set", upd and {"tag": "x", "value": "y"} in upd[0]["tags"] and {"tag": "unit", "value": "aishur"} in upd[0]["tags"])
check("existing host: its own macro created alone", ("usermacro.create", {"hostid": "H1", "macro": "{$GPU.TRAPPER.HOSTS}", "value": "192.168.0.9"}) in calls, calls)
imp = [p for m, p in calls if m == "configuration.import"]
check("import loads value maps and discovery rules", imp and "valueMaps" in imp[0]["rules"] and "discoveryRules" in imp[0]["rules"])
check("import reads the usage template file", imp and "template: 'GPU host usage'" in imp[0]["source"])

f = Fake(host={"hostid": "H1", "description": "", "parentTemplates": [], "tags": []}, macro={"hostmacroid": "M7"})
calls = run(f, pv.heat_host, "bridgeai-aishur", "192.168.0.9", "aishur", False)
check("existing macro: updated in place", ("usermacro.update", {"hostmacroid": "M7", "value": "192.168.0.9"}) in calls, calls)

f = Fake()
calls = run(f, pv.usage_host, "bridgeai-pc", "192.168.0.8", "pc", False)
cr = [p for m, p in calls if m == "host.create"]
check("new host: created with the template, tags, macro and the usage mark",
      cr and cr[0]["templates"] == [{"templateid": "T-GPU host usage"}] and cr[0]["macros"] == [{"macro": "{$GPU.TRAPPER.HOSTS}", "value": "192.168.0.8"}]
      and cr[0]["description"] == pv.USAGE_MARK, cr)
# Zabbix 7.0 import: a trapper item's allowed senders are `allowed_hosts` in the YAML (`trapper_hosts` is the API field and the import refuses it)
for t in ("template_gpu_usage.yaml", "template_gpu_heat.yaml", "template_provider_uptime.yaml"):
    src = open(os.path.join(HERE, "zabbix", t)).read()
    check(f"{t}: allowed_hosts, never trapper_hosts", "trapper_hosts:" not in src and "allowed_hosts:" in src)
# the fleet dashboard: every item-name pattern matches items the templates really have, and the per-service VRAM pattern catches only buckets
import fnmatch, re as _re
names = []
for t in ("template_gpu_usage.yaml", "template_gpu_heat.yaml"):
    names += _re.findall(r"^\s+name: '([^']+)'\n\s+type: TRAP", open(os.path.join(HERE, "zabbix", t)).read(), _re.M)
ws = pv.fleet_widgets(list(pv.FLEET_HOSTS), ["G1", "G2"])
pats = {f["value"] for w in ws if w["type"] == "svggraph" for f in w["fields"] if ".items." in f["name"]}
check("fleet: every item pattern matches a template item", all(any(fnmatch.fnmatchcase(n, p) for n in names) for p in pats),
      [p for p in pats if not any(fnmatch.fnmatchcase(n, p) for n in names)])
check("fleet: 'GPU *: VRAM' matches only the bucket prototype", [n for n in names if fnmatch.fnmatchcase(n, "GPU *: VRAM")] == ["GPU {#BUCKET}: VRAM"],
      [n for n in names if fnmatch.fnmatchcase(n, "GPU *: VRAM")])
check("fleet: widgets fit the 72-column grid and do not overlap",
      all(0 <= w["x"] and w["x"] + w["width"] <= 72 for w in ws) and
      not any(a is not b and a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]
              for a in ws for b in ws))
check("fleet: problems limited to the bridgeai groups", [f["value"] for f in ws[0]["fields"] if f["name"].startswith("groupids.")] == ["G1", "G2"])
f = Fake()
calls = run(f, pv.fleet_dashboard, list(pv.FLEET_HOSTS))
check("fleet: a new dashboard is created with one page", any(m == "dashboard.create" and len(p["pages"]) == 1 for m, p in calls))
sys.exit(1 if fails else 0)
