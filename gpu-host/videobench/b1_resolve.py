#!/usr/bin/env python3
"""B1 (Resolve part): the REF-60 edit built through Resolve Studio's scripting API, as far as the API allows, then rendered.
Needs a running Resolve (b1_resolve.sh starts a fresh one). Prints one JSON line with the timings and which steps the API
could do. Usage: python3 b1_resolve.py TAG"""
import json, os, sys, time
sys.path.insert(0, "/opt/resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr

tag = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser("~/Videos/vbench")   # Resolve renders only inside its Media Storage roots (~/Videos is one here)
os.makedirs(OUT, exist_ok=True)
res = {"tag": tag, "steps": {}}
t_all = time.time()
r = None
for _ in range(120):
    r = dvr.scriptapp("Resolve")
    if r and r.GetProjectManager():
        break
    time.sleep(1)
res["api_wait_s"] = round(time.time() - t_all, 1)
t = time.time()
pm = r.GetProjectManager()
name = f"vbench-ref60-{tag}-{int(time.time())}"
proj = pm.CreateProject(name)
for k, v in (("timelineResolutionWidth", "1920"), ("timelineResolutionHeight", "1080"), ("timelineFrameRate", "24")):
    proj.SetSetting(k, v)
mp = proj.GetMediaPool()
src, music, logo = mp.ImportMedia([f"{HERE}/ref/src90.mp4", f"{HERE}/inputs/music.mp3", f"{HERE}/ref/logo.png"])
tl = mp.CreateEmptyTimeline("ref60")
proj.SetCurrentTimeline(tl)
st = tl.GetStartFrame()
step = res["steps"]
items = mp.AppendToTimeline([{"mediaPoolItem": src, "startFrame": 240, "endFrame": 959},
                             {"mediaPoolItem": src, "startFrame": 1320, "endFrame": 2039}])
step["cuts"] = bool(items) and len(items) >= 2
step["crossfade"] = False   # no transition call in the scripting API
step["add_tracks"] = bool(tl.AddTrack("video")) and bool(tl.AddTrack("audio", "stereo"))
m = mp.AppendToTimeline([{"mediaPoolItem": music, "startFrame": 0, "endFrame": 1415, "mediaType": 2, "trackIndex": 2, "recordFrame": st}])
step["music_track"] = bool(m)
step["music_minus18db"] = bool(m) and bool(m[0].SetProperty("Volume", -18.0))
step["ducking"] = False     # no sidechain/ducking control in the scripting API (Fairlight automation is UI-only)
lg = mp.AppendToTimeline([{"mediaPoolItem": logo, "startFrame": 0, "endFrame": 1415, "trackIndex": 2, "recordFrame": st}])
step["logo"] = bool(lg) and bool(lg[0].SetProperty({"ZoomX": 0.5, "ZoomY": 0.5, "Pan": 760.0, "Tilt": 420.0}))
tl.SetCurrentTimecode(tl.GetStartTimecode()[:-2] + "24")   # 1 s in
title = tl.InsertFusionTitleIntoTimeline("Text+")
ok = False
if title:
    try:
        comp = title.GetFusionCompByIndex(1)
        tool = comp.FindToolByID("TextPlus") or next(iter((comp.GetToolList(False, "TextPlus") or {}).values()), None)
        ok = bool(tool) and tool.SetInput("StyledText", "Tears of Steel - benchmark") is not False
    except Exception as e:
        res["title_error"] = str(e)[:200]
step["title"] = ok
# SetLUT only accepts a file in Resolve's system LUT folder (absolute path, after RefreshLUTList); the user folder
# ~/.local/share/DaVinciResolve/LUT, a relative name, the node graph's SetLUT and opening the Color page all return False.
import shutil
lutdir = "/opt/resolve/LUT/vbench"
os.makedirs(lutdir, exist_ok=True)
shutil.copy(f"{HERE}/ref/grade.cube", lutdir)
proj.RefreshLUTList()
step["lut"] = all(i.SetLUT(1, f"{lutdir}/grade.cube") for i in items)
# Known API limits seen in the result: InsertFusionTitleIntoTimeline is a ripple insert (every track moves 5 s later, so the
# timeline ends at 64.9 s instead of 59.9 s) and fails when the other tracks are locked; a still (the logo) keeps the default
# 5 s length whatever endFrame says; endFrame is exclusive.
res["timeline_end_s"] = round((tl.GetEndFrame() - st) / 24, 2)
step["cdl"] = all(i.SetCDL({"NodeIndex": "1", "Slope": "1.0 1.0 1.0", "Offset": "0.05 0.05 0.05", "Power": "1.0 1.0 1.0",
                            "Saturation": "1.1"}) for i in items)
res["build_s"] = round(time.time() - t, 2)

out = {}
for label, fmt, want in (("h264", "mp4", ("264", "NVIDIA")), ("av1", "mp4", ("AV1", ""))):
    proj.DeleteAllRenderJobs()
    codecs = proj.GetRenderCodecs(fmt) or {}
    codec = next((v for k, v in codecs.items() if want[0] in k and want[1].upper() in k.upper()), None)
    if not codec:
        out[label] = {"error": f"no codec, have {list(codecs)}"}; continue
    proj.SetCurrentRenderFormatAndCodec(fmt, codec)
    proj.SetRenderSettings({"SelectAllFrames": True, "TargetDir": OUT, "CustomName": f"ref60-{tag}-{label}"})
    jid = proj.AddRenderJob()
    t = time.time()
    proj.StartRendering(jid)
    while proj.IsRenderingInProgress():
        time.sleep(0.2)
    s = proj.GetRenderJobStatus(jid)
    f = f"{OUT}/ref60-{tag}-{label}.mp4"
    out[label] = {"codec": codec, "status": s.get("JobStatus"), "render_s": round(s.get("TimeTakenToRenderInMs", (time.time() - t) * 1000) / 1000, 2),
                  "probe": os.popen(f"ffprobe -v error -show_entries format=duration,size -of csv=p=0 '{f}'").read().strip()}
res["render"] = out
res["total_s"] = round(time.time() - t_all, 1)
pm.SaveProject()
print(json.dumps(res), flush=True)
