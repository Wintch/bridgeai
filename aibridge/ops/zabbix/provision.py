#!/usr/bin/env python3
"""Create (and undo) the Zabbix 7.0 objects of the bridgeai ops hook, through the API. Design: ops/ZABBIX.md.

  python3 ops/zabbix/provision.py plan                  what `apply` would create, changes nothing
  python3 ops/zabbix/provision.py apply                 media type, secret macro, user + group, test group, the two actions (DISABLED)
  python3 ops/zabbix/provision.py test                  throwaway host with a trapper item and a High trigger: opens a problem, closes it,
                                                        reports what Zabbix sent (needs the actions enabled: `enable` first)
  python3 ops/zabbix/provision.py enable|disable        switch the two actions on / off
  python3 ops/zabbix/provision.py tag-hosts --group G --project P --unit U     put project and unit tags on every host of group G
  python3 ops/zabbix/provision.py untag-hosts --group G                        remove them again
  python3 ops/zabbix/provision.py targets --master M [--dry-run]   monitor the bridgeai machines in the master gateways.json M: one Zabbix host
                                                        per machine (grouped by address), one HTTP check per service (/healthz), no agent to install
  python3 ops/zabbix/provision.py untargets             delete the hosts `targets` created
  python3 ops/zabbix/provision.py rollback              delete everything this script created (the test host included)

Environment (never in git): ZBX_URL (the api_jsonrpc.php address), ZBX_TOKEN (API token of a Super admin), HOOK_TOKEN (the
receiver's ZBX_HOOK_TOKEN), HOOK_URL (http://<vm105>:8660/event). Secrets are sent, never printed.
Everything is found by name, so `apply` can be repeated. Only objects named `bridgeai*` / `{$BRIDGEAI_HOOK_TOKEN}` are touched, plus
the tags `project` and `unit` on the hosts of the group named in tag-hosts / untag-hosts.
"""
import argparse, json, os, secrets, string, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "bridgeai ops hook"
MACRO = "{$BRIDGEAI_HOOK_TOKEN}"
USER = "bridgeai-ops"
TEST_GROUP, TEST_HOST = "bridgeai/test", "bridgeai-test-hook"
ACTIONS = ("bridgeai notify-critical", "bridgeai notify-normal")
TAGS = ("project", "unit")
SEV_HIGH, SEV_AVERAGE = "4", "3"


def env(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"{name} is not set")
    return v


def api(method, params, auth=True):
    url = env("ZBX_URL").rstrip("/")
    if not url.endswith(".php"):
        url += "/api_jsonrpc.php"   # accept the site root as the URL
    req = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode(),
                                 headers={"Content-Type": "application/json-rpc", **({"Authorization": "Bearer " + env("ZBX_TOKEN")} if auth else {})})
    raw = urllib.request.urlopen(req, timeout=30).read()
    try:
        d = json.loads(raw)
    except ValueError:
        sys.exit(f"{method}: {url} did not answer JSON (first bytes: {raw[:60]!r}); check ZBX_URL")
    if "error" in d:
        sys.exit(f"{method}: {d['error'].get('message')} {d['error'].get('data', '')}")
    return d["result"]


def one(method, params):
    r = api(method, {**params, "output": "extend"} if "output" not in params else params)
    return r[0] if r else None


def require_super_admin():
    me = api("user.checkAuthentication", {"token": env("ZBX_TOKEN")}, auth=False)
    if str(me.get("type")) != "3":
        sys.exit("the token's user is not a Super admin")


def ensure(label, found, create):
    if found:
        print(f"  = {label}: exists")
        return found
    print(f"  + {label}: created")
    return create()


def media_params():
    return [{"name": n, "value": v} for n, v in [
        ("url", env("HOOK_URL")), ("token", MACRO), ("event_id", "{EVENT.ID}"), ("status", "{EVENT.STATUS}"),
        ("name", "{EVENT.NAME}"), ("severity", "{EVENT.SEVERITY}"), ("host", "{HOST.NAME}"), ("tags", "{EVENT.TAGSJSON}")]]


def apply(plan_only=False):
    require_super_admin()
    if plan_only:
        print("would create: host group", TEST_GROUP, "| secret macro", MACRO, "| media type", NAME, "| user group + user", USER,
              "(read on", TEST_GROUP, "and the groups named in READ_GROUPS) | actions", ", ".join(ACTIONS), "(disabled)")
        return
    tg = ensure("host group " + TEST_GROUP, one("hostgroup.get", {"filter": {"name": TEST_GROUP}}), lambda: {"groupid": api("hostgroup.create", {"name": TEST_GROUP})["groupids"][0]})
    ensure("macro " + MACRO, one("usermacro.get", {"globalmacro": True, "filter": {"macro": MACRO}}),
           lambda: api("usermacro.createglobal", {"macro": MACRO, "value": env("HOOK_TOKEN"), "type": 1, "description": "bridgeai ops hook: receiver token"}))
    script = open(os.path.join(HERE, "webhook_media_type.js")).read()
    mt_fields = {"name": NAME, "type": 4, "status": 0, "script": script, "parameters": media_params(), "timeout": "15s", "process_tags": 0, "show_event_menu": 0,
                 "maxattempts": 3, "attempt_interval": "10s", "description": "Posts problems and recoveries to the ops bot receiver (ops/zabbix_hook.py)",
                 "message_templates": [{"eventsource": 0, "recovery": 0, "subject": "{EVENT.NAME}", "message": "{EVENT.NAME}"},
                                       {"eventsource": 0, "recovery": 1, "subject": "{EVENT.NAME}", "message": "{EVENT.NAME}"}]}
    mt = ensure("media type " + NAME, one("mediatype.get", {"filter": {"name": NAME}}), lambda: {"mediatypeid": api("mediatype.create", mt_fields)["mediatypeids"][0]})
    cur = one("mediatype.get", {"filter": {"name": NAME}, "output": ["script", "status"]})
    if cur["script"] != script or cur["status"] != "0":   # a media type made through the API came out disabled: it must be on to send
        api("mediatype.update", {"mediatypeid": mt["mediatypeid"], "script": script, "parameters": media_params(), "status": 0})
        print("  ~ media type script, parameters and status (enabled) updated")
    read_names = [x for x in os.environ.get("READ_GROUPS", "").split(",") if x]
    found = api("hostgroup.get", {"output": ["groupid", "name"], "filter": {"name": read_names}}) if read_names else []   # an empty filter would match EVERY group
    if len(found) != len(read_names):
        sys.exit(f"READ_GROUPS names not all found: wanted {read_names}, found {[g['name'] for g in found]}")
    rights = [{"id": tg["groupid"], "permission": 2}] + [{"id": g["groupid"], "permission": 2} for g in found]
    ug = ensure("user group " + USER, one("usergroup.get", {"filter": {"name": USER}}),
                lambda: {"usrgrpid": api("usergroup.create", {"name": USER, "gui_access": 3, "hostgroup_rights": rights})["usrgrpids"][0]})
    api("usergroup.update", {"usrgrpid": ug["usrgrpid"], "hostgroup_rights": rights})
    pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(40))
    media = [{"mediatypeid": mt["mediatypeid"], "sendto": ["bridgeai"], "active": 0, "severity": 63, "period": "1-7,00:00-24:00"}]
    user = ensure("user " + USER, one("user.get", {"filter": {"username": USER}}),
                  lambda: {"userid": api("user.create", {"username": USER, "passwd": pw, "roleid": "1", "usrgrps": [{"usrgrpid": ug["usrgrpid"]}], "medias": media})["userids"][0]})
    def op():   # the same message operation for a problem and for its recovery
        return {"opmessage": {"default_msg": 1, "mediatypeid": mt["mediatypeid"]}, "opmessage_usr": [{"userid": user["userid"]}]}
    for name, sev_op, sev, step in ((ACTIONS[0], 5, SEV_HIGH, 1), (ACTIONS[1], 0, SEV_AVERAGE, 2)):
        ensure("action " + name, one("action.get", {"filter": {"name": name}}), lambda: {"actionid": api("action.create", {
            "name": name, "eventsource": 0, "status": 1, "esc_period": "5m", "pause_suppressed": 1,
            "filter": {"evaltype": 1, "conditions": [{"conditiontype": 4, "operator": sev_op, "value": sev}, {"conditiontype": 25, "operator": 0, "value": "unit"}]},
            "operations": [{"operationtype": 0, "esc_step_from": step, "esc_step_to": step, **op()}],
            "recovery_operations": [{"operationtype": 0, **op()}]})["actionids"][0]})
    print("done. The actions are disabled: run `test` after `enable`, `disable` to stop.")


def set_actions(status):
    for n in ACTIONS:
        a = one("action.get", {"filter": {"name": n}})
        if a:
            api("action.update", {"actionid": a["actionid"], "status": status})
    print("actions", "disabled" if status else "enabled")


def tag_hosts(group, project, unit, remove=False):
    g = one("hostgroup.get", {"filter": {"name": group}})
    if not g:
        sys.exit("no such host group")
    for h in api("host.get", {"groupids": g["groupid"], "output": ["host"], "selectTags": "extend"}):
        keep = [t for t in h["tags"] if t["tag"] not in TAGS]
        new = keep if remove else keep + [{"tag": "project", "value": project}, {"tag": "unit", "value": unit}]
        api("host.update", {"hostid": h["hostid"], "tags": new})
        print(f"  {'-' if remove else '+'} {h['host']}")


def test():
    require_super_admin()
    tg = one("hostgroup.get", {"filter": {"name": TEST_GROUP}})
    if not tg:
        sys.exit("run apply first")
    host = ensure("test host " + TEST_HOST, one("host.get", {"filter": {"host": TEST_HOST}}), lambda: {"hostid": api("host.create", {
        "host": TEST_HOST, "groups": [{"groupid": tg["groupid"]}], "tags": [{"tag": "project", "value": "bridgeai"}, {"tag": "unit", "value": "test"}]})["hostids"][0]})
    ensure("trapper item", one("item.get", {"hostids": host["hostid"], "filter": {"key_": "test.value"}}), lambda: api("item.create", {
        "hostid": host["hostid"], "name": "test value", "key_": "test.value", "type": 2, "value_type": 3}))
    ensure("High trigger", one("trigger.get", {"hostids": host["hostid"], "output": ["description"]}), lambda: api("trigger.create", {
        "description": "bridgeai hook test", "expression": f"last(/{TEST_HOST}/test.value)>0", "priority": int(SEV_HIGH),
        "tags": [{"tag": "service", "value": "test"}, {"tag": "tier", "value": "critical"}]}))
    def wait_for(label, cond, secs=150):
        end = time.time() + secs
        while time.time() < end:
            r = cond()
            if r:
                return r
            time.sleep(5)
        sys.exit(f"timeout waiting for {label}")
    item = one("item.get", {"hostids": host["hostid"], "filter": {"key_": "test.value"}, "output": ["itemid"]})
    def push_until_seen(value):
        """The server learns a new host/item on its next configuration sync (up to ~60 s) and drops a value pushed before that, silently:
        push again until the item reports a newer value."""
        before = int(one("item.get", {"itemids": item["itemid"], "output": ["lastclock"]})["lastclock"])
        for _ in range(10):
            api("history.push", [{"host": TEST_HOST, "key": "test.value", "value": value}])
            time.sleep(15)
            if int(one("item.get", {"itemids": item["itemid"], "output": ["lastclock"]})["lastclock"]) > before:
                return
            print("  the server has not taken the value yet (configuration sync); pushing again")
        sys.exit("the value never arrived: is the trapper item known to the server?")
    for value, label in ((1, "problem"), (0, "recovery")):
        push_until_seen(value)
        print(f"pushed value {value}, received; waiting for the {label}")
        if value:
            wait_for("a problem", lambda: api("problem.get", {"hostids": host["hostid"], "output": ["eventid"]}))
        else:
            wait_for("the problem to close", lambda: not api("problem.get", {"hostids": host["hostid"], "output": ["eventid"]}))
        time.sleep(15)
        alerts = api("alert.get", {"output": ["status", "error", "retries"], "sortfield": "clock", "sortorder": "DESC", "limit": 2, "mediatypeids": one("mediatype.get", {"filter": {"name": NAME}})["mediatypeid"]})
        print("  alerts (newest first; status 1 = sent, 2 = failed, 0 = in progress):", [(a["status"], a["error"][:100]) for a in alerts])


MARK = "managed by ops/zabbix/provision.py targets"
TIER_SEVERITY = {"critical": 4, "normal": 3, "info": 1}   # info = Information: no action matches it, dashboard only
STATUS_RE = "HTTP\\/[0-9.]+ ([0-9]+)\n\\1"            # retrieve only the headers; keep the status code


def build_targets(master):
    """[{unit, addr, tier, checks: [{service, url}]}] from the master gateways.json. Machines are grouped by address (the 3060 Ti has two
    entries); the first entry's name is the unit. A service on a second entry with another port gets that entry's name as a suffix.
    An `always_on: false` machine (a PC that sleeps or runs VR) is tier `info`: it is expected to be off, so it must not page."""
    by_addr = {}
    for key, h in master.get("hosts", {}).items():
        if "addr" not in h:
            continue
        t = by_addr.setdefault(h["addr"], {"unit": key, "addr": h["addr"], "tier": "critical" if h.get("always_on") else "info", "ports": {}})
        if h.get("always_on"):
            t["tier"] = "critical"
        for kind in ("transcode", "upscale", "stt", "tts", "llm"):
            if h.get(kind):
                if h[kind] in t["ports"].values():
                    continue
                t["ports"][kind if kind not in t["ports"] else f"{kind}-{key}"] = h[kind]
    out = []
    for t in by_addr.values():
        checks = [{"service": svc, "url": f"http://{t['addr']}:{port}" + ("/health" if svc.startswith("llm") else "/healthz")} for svc, port in t["ports"].items()]
        out.append({"unit": t["unit"], "addr": t["addr"], "tier": t["tier"], "checks": checks})
    return out


def targets(master_path, dry):
    require_super_admin()
    try:
        master = json.load(open(master_path))
    except (OSError, ValueError) as e:
        sys.exit(f"cannot read the master gateways.json at {master_path} as JSON ({type(e).__name__}); with a process substitution quote the remote path, e.g. <(ssh host 'cat ~/aibridge/ops/gateways.json')")
    plan = build_targets(master)
    for t in plan:
        print(f"  unit {t['unit']} (tier {t['tier']}): " + ", ".join(c["service"] for c in t["checks"]))
    if dry:
        print("dry run: nothing created")
        return
    ug = one("usergroup.get", {"filter": {"name": USER}, "selectHostGroupRights": "extend", "output": ["usrgrpid"]})
    if not ug:
        sys.exit("run apply first")
    rights = {r["id"]: r["permission"] for r in ug["hostgroup_rights"]}
    for t in plan:
        gname, hname = f"bridgeai/{t['unit']}", f"bridgeai-{t['unit']}"
        grp = ensure("host group " + gname, one("hostgroup.get", {"filter": {"name": gname}}), lambda: {"groupid": api("hostgroup.create", {"name": gname})["groupids"][0]})
        rights[grp["groupid"]] = "2"
        host = ensure("host " + hname, one("host.get", {"filter": {"host": hname}, "output": ["hostid"]}), lambda: {"hostid": api("host.create", {
            "host": hname, "description": MARK, "groups": [{"groupid": grp["groupid"]}],
            "interfaces": [{"type": 1, "main": 1, "useip": 1, "ip": t["addr"], "dns": "", "port": "10050"}],   # never polled: the checks are HTTP agent items
            "tags": [{"tag": "project", "value": "bridgeai"}, {"tag": "unit", "value": t["unit"]}]})["hostids"][0]})
        iface = api("hostinterface.get", {"hostids": host["hostid"], "output": ["interfaceid"]})[0]["interfaceid"]
        for c in t["checks"]:
            key = f"health[{c['service']}]"
            ensure(f"  item {key}", one("item.get", {"hostids": host["hostid"], "filter": {"key_": key}, "output": ["itemid"]}), lambda: api("item.create", {
                "hostid": host["hostid"], "interfaceid": iface, "name": f"{c['service']} health", "key_": key, "type": 19, "value_type": 3, "url": c["url"],
                "request_method": 0, "retrieve_mode": 1, "timeout": "5s", "delay": "1m", "history": "14d", "trends": "90d",
                "preprocessing": [{"type": "5", "params": STATUS_RE, "error_handler": "0", "error_handler_params": ""}]}))
            ensure(f"  trigger {key}", one("trigger.get", {"hostids": host["hostid"], "filter": {"description": f"{c['service']} health check failing"}, "output": ["triggerid"]}), lambda: api("trigger.create", {
                "description": f"{c['service']} health check failing",
                "expression": f"last(/{hname}/{key})<>200 or nodata(/{hname}/{key},5m)", "priority": TIER_SEVERITY[t["tier"]],
                "tags": [{"tag": "service", "value": c["service"]}, {"tag": "tier", "value": t["tier"]}]}))
    api("usergroup.update", {"usrgrpid": ug["usrgrpid"], "hostgroup_rights": [{"id": i, "permission": p} for i, p in rights.items()]})
    print("done. A unit with tier info shows on the dashboard and never sends; critical sends at once.")


def agent_host(name, addr, unit, project, template):
    """A host polled by the Zabbix agent (passive, port 10050) with a template; it carries `project` and `unit`, so its triggers page by severity."""
    require_super_admin()
    ug = one("usergroup.get", {"filter": {"name": USER}, "selectHostGroupRights": "extend", "output": ["usrgrpid"]})
    if not ug:
        sys.exit("run apply first")
    tpl = one("template.get", {"filter": {"host": template}, "output": ["templateid"]})
    if not tpl:
        sys.exit(f"template {template!r} not found")
    gname = f"bridgeai/{unit}"
    grp = ensure("host group " + gname, one("hostgroup.get", {"filter": {"name": gname}}), lambda: {"groupid": api("hostgroup.create", {"name": gname})["groupids"][0]})
    ensure("host " + name, one("host.get", {"filter": {"host": name}, "output": ["hostid"]}), lambda: api("host.create", {
        "host": name, "description": MARK, "groups": [{"groupid": grp["groupid"]}], "templates": [{"templateid": tpl["templateid"]}],
        "interfaces": [{"type": 1, "main": 1, "useip": 1, "ip": addr, "dns": "", "port": "10050"}],
        "tags": [{"tag": "project", "value": project}, {"tag": "unit", "value": unit}]}))
    rights = {r["id"]: r["permission"] for r in ug["hostgroup_rights"]}
    rights[grp["groupid"]] = "2"
    api("usergroup.update", {"usrgrpid": ug["usrgrpid"], "hostgroup_rights": [{"id": i, "permission": p} for i, p in rights.items()]})
    print("done. The agent must list the Zabbix server in its Server= setting; availability shows on the host in a minute or two.")


def untargets():
    require_super_admin()
    for h in api("host.get", {"output": ["host", "description"], "search": {"host": "bridgeai-"}}):
        if h["description"] == MARK:
            api("host.delete", [h["hostid"]]); print("  - host", h["host"])
    for g in api("hostgroup.get", {"output": ["name"], "search": {"name": "bridgeai/"}}):
        if g["name"] != TEST_GROUP and not api("host.get", {"groupids": g["groupid"], "output": ["hostid"], "limit": 1}):
            api("hostgroup.delete", [g["groupid"]]); print("  - host group", g["name"])


def rollback():
    require_super_admin()
    untargets()
    for n in ACTIONS:
        a = one("action.get", {"filter": {"name": n}})
        if a:
            api("action.delete", [a["actionid"]]); print("  - action", n)
    for kind, getter, ident, flt, label in (("user", "user.get", "userid", {"username": USER}, USER), ("user group", "usergroup.get", "usrgrpid", {"name": USER}, USER),
                                            ("host", "host.get", "hostid", {"host": TEST_HOST}, TEST_HOST), ("media type", "mediatype.get", "mediatypeid", {"name": NAME}, NAME)):
        o = one(getter, {"filter": flt, "output": [ident]})
        if o:
            api(getter.replace(".get", ".delete"), [o[ident]]); print("  -", kind, label)
    m = one("usermacro.get", {"globalmacro": True, "filter": {"macro": MACRO}})
    if m:
        api("usermacro.deleteglobal", [m["globalmacroid"]]); print("  - macro", MACRO)
    g = one("hostgroup.get", {"filter": {"name": TEST_GROUP}})
    if g:
        api("hostgroup.delete", [g["groupid"]]); print("  - host group", TEST_GROUP)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "apply", "test", "enable", "disable", "tag-hosts", "untag-hosts", "targets", "untargets", "agent-host", "rollback"])
    ap.add_argument("--group"); ap.add_argument("--project"); ap.add_argument("--unit"); ap.add_argument("--master"); ap.add_argument("--name"); ap.add_argument("--addr"); ap.add_argument("--template", default="Linux by Zabbix agent"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "plan":
        apply(plan_only=True)
    elif a.cmd == "apply":
        apply()
    elif a.cmd == "test":
        test()
    elif a.cmd in ("enable", "disable"):
        require_super_admin(); set_actions(0 if a.cmd == "enable" else 1)
    elif a.cmd == "tag-hosts":
        if not (a.group and a.project and a.unit):
            sys.exit("tag-hosts needs --group --project --unit")
        tag_hosts(a.group, a.project, a.unit)
    elif a.cmd == "targets":
        if not a.master:
            sys.exit("targets needs --master (the master gateways.json)")
        targets(a.master, a.dry_run)
    elif a.cmd == "agent-host":
        if not (a.name and a.addr and a.unit):
            sys.exit("agent-host needs --name --addr --unit (and optionally --project, --template)")
        agent_host(a.name, a.addr, a.unit, a.project or "bridgeai", a.template)
    elif a.cmd == "untargets":
        untargets()
    elif a.cmd == "untag-hosts":
        if not a.group:
            sys.exit("untag-hosts needs --group")
        tag_hosts(a.group, "", "", remove=True)
    else:
        rollback()
