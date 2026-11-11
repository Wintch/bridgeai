"""ComfyUI benchmark for fast SDXL variants on the GPU workstation, same method as comfy_bench.py:
start the real server headless, queue a standard txt2img workflow through its API, time each image server-side.

  bench_fast.py TAG CKPT STEPS CFG SAMPLER SCHEDULER [runs]      env: W, H (default 1024), SEEDS=1000 (first seed)

Runs inside the comfy-bench container with ~/imggen mounted at /w, the base checkpoints at /models/base and the
gpu-media checkpoints at /models/gpu (see sweep_fast.sh). Three prompts cycle with fixed seeds so the images of
different variants can be compared by eye. The first image includes the model load (warm-up) and is reported apart."""
import json, os, subprocess, sys, time, urllib.request

tag, ckpt, steps, cfg, sampler, sched = sys.argv[1:7]
runs = int(sys.argv[7]) if len(sys.argv) > 7 else 7
W, H = int(os.environ.get("W", 1024)), int(os.environ.get("H", 1024))
seed0 = int(os.environ.get("SEEDS", 1000))
PROMPTS = ["a red fox sitting in a snowy pine forest at sunrise, golden light, detailed fur, photo",
           "studio portrait of an elderly fisherman with a weathered face, soft window light, 85mm photo",
           "a ceramic coffee mug on a wooden table next to a window, morning light, product photo"]
URL = "http://127.0.0.1:8188"
os.makedirs("/w/out/fast", exist_ok=True)
log = open(f"/w/out/fast-{tag}.log", "w")
srv = subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188", "--output-directory", "/w/out/fast",
                        "--extra-model-paths-config", "/w/extra_paths.yaml", "--disable-auto-launch"], cwd="/w/ComfyUI", stdout=log, stderr=subprocess.STDOUT)
t_srv = time.time()
for _ in range(240):
    try:
        urllib.request.urlopen(URL + "/system_stats", timeout=2); break
    except Exception:
        time.sleep(0.5)
ready_s = round(time.time() - t_srv, 1)


def wf(i):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": PROMPTS[i % 3]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "blurry, low quality, watermark"}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": W, "height": H, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
              "seed": seed0 + i, "steps": int(steps), "cfg": float(cfg), "sampler_name": sampler, "scheduler": sched, "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": f"{tag}-p{i % 3}-s{seed0 + i}"}},
    }


def post(path, body):
    req = urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


secs = []
for i in range(runs):
    pid = post("/prompt", {"prompt": wf(i)})["prompt_id"]
    while True:
        h = json.load(urllib.request.urlopen(f"{URL}/history/{pid}", timeout=10))
        if pid in h and h[pid]["status"].get("completed") is not None:
            break
        time.sleep(0.25)
    st = h[pid]["status"]
    if st.get("status_str") == "error":
        print(json.dumps({"tag": tag, "error": str(st.get("messages"))[-300:]})); break
    msgs = {m[0]: m[1].get("timestamp") for m in st["messages"]}
    secs.append(round((msgs["execution_success"] - msgs["execution_start"]) / 1000, 2))
srv.terminate(); srv.wait(30); log.close()
print(json.dumps({"tag": tag, "ckpt": ckpt, "size": f"{W}x{H}", "steps": int(steps), "cfg": float(cfg), "sampler": sampler, "scheduler": sched,
                  "server_ready_s": ready_s, "warmup_s": secs[0] if secs else None, "image_s": secs[1:],
                  "power_limit": os.popen("nvidia-smi --query-gpu=power.limit --format=csv,noheader").read().strip()}))
