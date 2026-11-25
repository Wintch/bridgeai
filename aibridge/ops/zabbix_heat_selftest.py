#!/usr/bin/env python3
"""Offline check that the GPU host heat template and the gate's push agree: every key the gate sends is an item of the template,
every trigger reads items that exist and also needs fresh data (a sleeping machine is not an alarm). Run: python3 -I ops/zabbix_heat_selftest.py"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "gpu-host", "gate"))
import host_control as hc  # noqa: E402

tpl = open(os.path.join(HERE, "zabbix", "template_gpu_heat.yaml")).read()
fails = []


def check(label, got, want):
    print(("ok   " if got == want else "FAIL ") + label)
    if got != want:
        fails.append(label); print("     got ", got, "\n     want", want)


keys = sorted(re.findall(r"^\s+key: '([^']+)'", tpl, re.M))
sent = sorted({k for _, k, _ in hc.zbx_items("h", {"level": "ok", "gpu_c": 1.0, "gpu_w": 1.0, "cpu_c": 1.0, "throttle": []})})
check("the gate sends exactly the template's item keys", sent, keys)
exprs = re.findall(r"^\s+expression: '([^']+)'", tpl, re.M)
check("three triggers", len(exprs), 3)
check("every trigger reads only template items", sorted({k for e in exprs for k in re.findall(r"/GPU host heat/([a-z_.]+)", e)}), sorted(set(keys) & {"heat.level", "heat.slowdown"}))
check("every trigger needs data newer than {$HEAT.NODATA}", all("nodata(" in e and "{$HEAT.NODATA})=0" in e for e in exprs), True)
check("no trigger fires on missing data (no nodata()=1)", any("=1" in e.split("nodata(")[-1] for e in exprs), False)
check("the host-only trapper macro default refuses everyone", "macro: '{$HEAT.TRAPPER.HOSTS}'\n          value: 127.0.0.1" in tpl, True)
check("provision.py loads this template by this name", ('HEAT_TEMPLATE = "GPU host heat"' in open(os.path.join(HERE, "zabbix", "provision.py")).read(), "template: 'GPU host heat'" in tpl), (True, True))
sys.exit(1 if fails else 0)
