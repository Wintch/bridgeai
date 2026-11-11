#!/usr/bin/env python3
"""Print the nodes of a ComfyUI blueprint (UI format, with subgraphs): type, widget values and links, to hand-write API prompts."""
import json, sys

bp = json.load(open(sys.argv[1]))


def dump(nodes, links, ind=""):
    lk = {}
    for l in links or []:
        if isinstance(l, dict):
            lk[l["id"]] = (l["origin_id"], l["origin_slot"])
        else:
            lk[l[0]] = (l[1], l[2])
    for n in sorted(nodes, key=lambda n: n.get("order", 0)):
        ins = []
        for i in n.get("inputs") or []:
            if i.get("link") is not None:
                ins.append(f"{i['name']}<-{lk.get(i['link'])}")
        print(f"{ind}#{n['id']} {n['type']} {json.dumps(n.get('widgets_values'))[:300]} {' '.join(ins)}")


dump(bp.get("nodes", []), bp.get("links"))
for sg in (bp.get("definitions") or {}).get("subgraphs", []):
    print("-- subgraph", sg.get("name"))
    dump(sg.get("nodes", []), sg.get("links"), "  ")
