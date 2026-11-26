#!/usr/bin/env python3
"""Offline checks for place-desktop-links against a fake home (Steam libraries, Heroic's installed list). Run: python3 -I desktop_links_selftest.py"""
import importlib.machinery, importlib.util, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
fails = 0


def check(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    fails += 0 if ok else 1


home = tempfile.mkdtemp()
os.environ["HOME"] = home
os.environ["PATH"] = "/nonexistent"                 # no xdg-user-dir, no gio: the script must still work
loader = importlib.machinery.SourceFileLoader("pdl", os.path.join(HERE, "place-desktop-links"))
spec = importlib.util.spec_from_loader("pdl", loader)
pdl = importlib.util.module_from_spec(spec)
loader.exec_module(pdl)
pdl.HOME = home
pdl.STEAM_ROOTS = [os.path.join(home, ".steam", "debian-installation")]
root, extra = pdl.STEAM_ROOTS[0], os.path.join(home, "Extra", "SteamLibrary")
for d in (os.path.join(root, "steamapps"), os.path.join(extra, "steamapps")):
    os.makedirs(d)
open(os.path.join(root, "steamapps", "libraryfolders.vdf"), "w").write(f'"libraryfolders"\n{{\n "0" {{ "path" "{root}" }}\n "1" {{ "path" "{extra}" }}\n}}\n')
man = lambda d, appid, name, flags=4: open(os.path.join(d, "steamapps", f"appmanifest_{appid}.acf"), "w").write(f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"StateFlags"\t\t"{flags}"\n}}\n')
man(root, 12210, "Grand Theft Auto IV")
man(extra, 612880, "Wolfenstein II")
man(root, 1493710, "Proton Experimental")
man(root, 228980, "Steamworks Common Redistributables")
man(root, 999, "Half downloaded", flags=1026)
man(root, 777, "Evil\nExec=rm -rf /")
icon = os.path.join(home, ".local", "share", "icons", "hicolor", "32x32", "apps")
os.makedirs(icon)
open(os.path.join(icon, "steam_icon_12210.png"), "wb").write(b"png")
hd = os.path.join(home, ".config", "heroic", "legendaryConfig", "legendary")
os.makedirs(hd)
open(os.path.join(hd, "installed.json"), "w").write('{"Fortnite": {"title": "Some Epic Game"}, "bad name;rm": {"title": "x"}}')
desk = os.path.join(home, "Desktop")
os.makedirs(desk)
open(os.path.join(desk, "mine.desktop"), "w").write("[Desktop Entry]\nName=Mine\n")
n, c = pdl.sync()
files = sorted(os.listdir(desk))
check("one icon per installed game, in every Steam library", "bridgeai-steam-12210.desktop" in files and "bridgeai-steam-612880.desktop" in files, files)
check("Proton, redistributables and half-downloaded games get no icon", not any(x in " ".join(files) for x in ("1493710", "228980", "999")), files)
g = open(os.path.join(desk, "bridgeai-steam-12210.desktop")).read()
check("a Steam game starts through steam://rungameid with Steam's own icon", "Exec=steam steam://rungameid/12210" in g and "steam_icon_12210.png" in g, g)
evil = open(os.path.join(desk, "bridgeai-steam-777.desktop")).read()
check("a name with a newline cannot add lines to the launcher", [l for l in evil.splitlines() if l.startswith("Exec=")] == ["Exec=steam steam://rungameid/777"], evil)
check("an Epic game installed through Heroic gets an icon; a strange app name does not", "bridgeai-epic-Fortnite.desktop" in files and not any("rm" in x for x in files), files)
check("launchers are executable", os.access(os.path.join(desk, "bridgeai-steam-12210.desktop"), os.X_OK))
check("the person's own icons are left alone", "mine.desktop" in files)
os.remove(os.path.join(extra, "steamapps", "appmanifest_612880.acf"))
n2, c2 = pdl.sync()
files = sorted(os.listdir(desk))
check("an uninstalled game's icon goes away, nothing else changes", "bridgeai-steam-612880.desktop" not in files and c2 == 1 and "mine.desktop" in files, (c2, files))
print("desktop_links_selftest: " + ("all ok" if not fails else f"{fails} failed"))
sys.exit(1 if fails else 0)
