#!/usr/bin/env python3
"""Offline checks for places-net.sh with fake ip and nft. Run: python3 -I places_net_selftest.py"""
import os, subprocess, sys, tempfile
import atexit as _a, shutil as _s
tmp = tempfile.mkdtemp(prefix="selftest-"); _a.register(_s.rmtree, tmp, True)
HERE = os.path.dirname(os.path.abspath(__file__))
log = os.path.join(tmp, "calls.txt"); have = os.path.join(tmp, "have")
open(have, "w").write("")
open(os.path.join(tmp, "ip"), "w").write(f'''#!/bin/sh
echo "ip $@" >> {log}
case "$*" in
  "-4 route show default") echo "default via 10.9.8.1 dev lan7 proto dhcp";;
  "-4 -o addr show dev lan7 scope global") echo "2: lan7    inet 10.9.8.7/24 brd 10.9.8.255 scope global dynamic lan7";;
  "-4 -o addr show dev lan7") echo "2: lan7    inet 10.9.8.7/24 scope global lan7"; cat {have};;
esac
case "$1" in addr) [ "$2" = add ] && echo "inet $3 " >> {have};; esac
exit 0
''')
open(os.path.join(tmp, "nft"), "w").write(f'#!/bin/sh\necho "nft $@" >> {log}\n[ "$1" = "-f" ] && cat >> {log}\nexit 0\n')
for n in ("ip", "nft"):
    os.chmod(os.path.join(tmp, n), 0o755)
conf = os.path.join(tmp, "conf"); open(conf, "w").write("PLACE_IPS=(10.9.8.8 10.9.8.9)\n")
env = dict(os.environ, IP=os.path.join(tmp, "ip"), NFT=os.path.join(tmp, "nft"), PLACES_NET_CONF=conf)
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def run(*a, e=None):
    return subprocess.run(["bash", os.path.join(HERE, "places-net.sh"), *a], capture_output=True, text=True, env=e or env)


r = run("print")
rs = r.stdout
check("the ruleset lets answers to the LAN's own connections through BEFORE it drops", rs.index("established,related accept") < rs.index("drop"), rs)
check("it drops a place's traffic to every private, link-local and CGNAT range", all(x in rs for x in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10")) and "ip saddr 172.30.0.0/16" in rs, rs)
check("it acts in the forward path, ahead of docker's own chain, and accepts the rest (the internet)", "hook forward priority -5; policy accept" in rs, rs)
r = run("print")
check("no game port: no exception between places in the ruleset", "udp dport" not in r.stdout, r.stdout)
open(conf, "w").write("PLACE_IPS=(10.9.8.8 10.9.8.9)\nPLACE_GAME_UDP=(27960 27961)\n")
r = run("print")
check("a game UDP port opens exactly that port between the places, before the drop and for nothing else", "ip saddr 172.30.0.0/16 ip daddr 172.30.0.0/16 udp dport { 27960, 27961 } accept" in r.stdout and r.stdout.index("udp dport") < r.stdout.index("drop"), r.stdout)
for bad in ("80", "99999", "abc"):
    open(conf, "w").write(f"PLACE_GAME_UDP=({bad})\n")
    check(f"a bad game port ({bad}) is refused", run("print").returncode == 2)
open(conf, "w").write("PLACE_IPS=(10.9.8.8 10.9.8.9)\n")
r = run("up")
calls = open(log).read()
check("up finds the LAN interface from the default route and adds each address with the interface's prefix", "ip addr add 10.9.8.8/24 dev lan7" in calls and "ip addr add 10.9.8.9/24 dev lan7" in calls and r.returncode == 0, calls + r.stderr)
check("up loads the table (the old one removed first)", "nft delete table inet bridgeai_places" in calls and "nft -f -" in calls and "table inet bridgeai_places" in calls, calls)
open(log, "w").close()
r = run("up")
check("up twice adds nothing twice", "ip addr add" not in open(log).read() and "already on lan7" in r.stdout, r.stdout + open(log).read())
r = run("status")
check("status says which addresses are up and whether the firewall is loaded", "10.9.8.8: up" in r.stdout and "firewall: loaded" in r.stdout, r.stdout)
open(log, "w").close()
r = run("down")
c = open(log).read()
check("down removes the addresses and the table", "ip addr del 10.9.8.8/24 dev lan7" in c and "nft delete table inet bridgeai_places" in c, c)
for bad in ("8.8.8.8", "0.0.0.0", "172.32.0.1", "10.9.8"):
    open(conf, "w").write(f"PLACE_IPS=({bad})\n")
    r = run("up")
    check(f"a public or odd address ({bad}) is refused before anything changes", r.returncode == 2 and "ip addr add" not in open(log).read().split("refused")[-1], r.stderr)
open(conf, "w").write("PLACE_IPS=(10.9.8.8)\nPLACE_IFACE=eth9\n")
open(log, "w").close()
run("up")
check("PLACE_IFACE overrides the default-route lookup", "dev eth9" in open(log).read() or "-4 -o addr show dev eth9 scope global" in open(log).read(), open(log).read())
check("an unknown verb is usage, rc 2", run("fly").returncode == 2)
print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
