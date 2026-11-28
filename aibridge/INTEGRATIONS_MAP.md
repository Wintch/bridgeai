# Integrations map: APIs and MCP servers

This is a map of every API and MCP integration bridgeai already knows how to use, drawn from the code and docs in this repo.
It covers four views: the whole system, the APIs by purpose, the MCP servers with their guards, and what is only planned.
Planned or designed items are drawn dashed and labelled "planned"; nothing dashed is in production.
Names are generic on purpose: "the VM", "the GPU workstation", "the machine-power provider (sibling project)", and "the stacks" (one Hermes per person).
The inventory table at the end lists every integration with its kind, where it runs, who holds the key, its status and its source file.

## Legend

| Drawing | Meaning |
|---|---|
| Solid box and solid arrow | In production (or built and used on demand) |
| Dashed box and dashed arrow | Designed, planned or pilot only: not in production |
| Thick arrow | An MCP server behind a server-side guard (today a block-list filter or confined folders; an allow-list mode is planned) |
| Pale-blue box | Component of bridgeai or a service it runs |
| Grey box | Third-party service outside our control |
| Green box with a thick border | MCP server |
| Amber dashed box | Planned |

Privacy classes A, B and C (where a person's data may go) are defined in `DATA_LAW_AND_KEYS.md`.

Status words used below: "live" means the repo documents it as running; "on demand" means the GPU workstation services, which are kept stopped and started when needed; "pilot" means built and tested but not deployed.

## 1. Overview

```mermaid
flowchart LR
  subgraph CH["Channels"]
    PPL["People (es, ru, en)"]
    TGC["Telegram, one bot per person"]
    TGL["Local Bot API server (files up to 2 GB)"]
    WEB["Open WebUI web chat"]
    VPX["Voice proxy (speech in and out)"]
    OPSB["Ops bot (operator alerts and chat)"]
    ZH["Zabbix webhook receiver"]
  end
  subgraph STK["Per-person Hermes stacks on the VM"]
    S1["operator stack"]
    S2["person stack 2"]
    S3["person stack 3"]
    S4["person stack 4"]
    AG["Hermes agent: own memory, keys, files"]
    RT["router: model choice, consent, cooldowns"]
    GW["gateway facade (one CLI)"]
    MC["Hermes MCP client"]
  end
  subgraph HS["VM host services"]
    WK["waker: sleep and wake on demand"]
    HUB["hub collector (read-only feeds)"]
    SCN["scan service (ClamAV, file queue)"]
    OPSV["backup, telemetry, key and model guards"]
  end
  subgraph EXT["Outside the VM"]
    MOD["Model providers"]
    APIS["Public and keyed data APIs"]
    SEC["abuse.ch and CIRCL hash lookups"]
    INF["Zabbix and Proxmox APIs (read-only)"]
    WSITE["Website git repo, deploy webhook, Pages"]
    CCM["Claude Code machine (SSH gate)"]
  end
  subgraph WSN["GPU workstation"]
    GPUS["transcoder, upscaler, STT, TTS, local LLM, image (v0)"]
    MR["Resolve MCP: community and vendor"]
    EC["EffectCraft MCP"]
  end
  subgraph PL["Planned or pilot"]
    POOL["pool broker, selector, presence, lease (planned)"]
    DES["design pack: ComfyUI, Blender, Craft MCPs"]
    ADB["official Adobe MCP (not decided)"]
    MPW["machine-power provider (sibling project)"]
    HCM["hostcare MCP and ops brain (pilot)"]
  end

  PPL --> TGC
  PPL --> WEB
  TGC --> TGL
  TGL --> S1
  TGL --> S2
  TGL --> S3
  TGL --> S4
  WEB --> VPX
  WEB --> S1
  WEB --> S2
  WEB --> S3
  WEB --> S4
  VPX --> GPUS
  S1 --> AG
  S2 --> AG
  S3 --> AG
  S4 --> AG
  AG --> RT
  AG --> GW
  AG --> MC
  WK -->|"sleep and wake"| AG
  HUB -->|"read-only mount"| AG
  RT --> MOD
  GW --> APIS
  GW --> SEC
  GW --> INF
  GW --> WSITE
  GW --> CCM
  GW --> GPUS
  GW -->|"file queue"| SCN
  MC ==>|"ssh forced command"| MR
  MC ==>|"ssh forced command"| EC
  INF -->|"webhook"| ZH
  ZH --> OPSB
  OPSV --> OPSB
  GW -.->|"planned"| POOL
  POOL -.-> GPUS
  POOL -.->|"planned"| MPW
  DES -.-> POOL
  MC -.->|"planned"| ADB
  MC -.->|"pilot"| HCM

  classDef live fill:#e8f1ff,stroke:#2b5fb4,color:#111;
  classDef ext fill:#f1f1f1,stroke:#555,color:#111;
  classDef mcp fill:#e4f6e8,stroke:#1b7a3a,color:#111,stroke-width:3px;
  classDef planned fill:#fff4d6,stroke:#b07800,color:#111,stroke-dasharray: 5 5;
  class PPL,TGC,TGL,WEB,VPX,OPSB,ZH,S1,S2,S3,S4,AG,RT,GW,MC,WK,HUB,SCN,OPSV,GPUS live;
  class MOD,APIS,SEC,INF,WSITE,CCM ext;
  class MR,EC mcp;
  class POOL,DES,ADB,MPW,HCM planned;
```

### 1.1 A message's path, in time

A person writes on Telegram while their stack sleeps (the usual case). Roles, not machine names: the **wake VM** is always on
(Wake-on-LAN, the Local Bot API servers, watchers); the **Docker host** holds every stack and suspends itself when idle; the
**always-on VM** holds each person's data; the **GPU host** sleeps unless a task needs it.

```mermaid
sequenceDiagram
  autonumber
  actor P as Person
  participant TG as Telegram
  participant WV as Wake VM: Local Bot API + watcher
  participant DH as Docker host: waker
  participant H as Stack: Hermes gateway
  participant PL as aibridge-controls plugin
  participant R as Router (in the stack)
  participant M as Model provider (HTTPS)
  participant G as GPU host: gate
  participant D as Always-on VM: data (NFS)

  P->>TG: message
  TG->>WV: update reaches the Local Bot API server (polled)
  alt Docker host asleep
    WV->>DH: Wake-on-LAN magic packet
    WV-->>P: "waking up" notice (deletes itself)
  end
  DH->>WV: getUpdates peek, not confirmed (who has mail?)
  DH->>H: start the brain (RAM guard, admit)
  H->>D: persist and workdir mounted over NFS
  H->>WV: getUpdates (confirms), over the stack's bridge
  alt slash command (/produccion, /lgtm, /dormir, /settings...)
    H->>PL: handled before the model, the person's own action
    PL-->>P: reply (and its action, e.g. publish starts)
  else a normal message
    H->>R: model call (OpenAI-compatible HTTP, inside the container)
    Note over R: reply-language note per message,<br/>pack hints, request cap, route by policy
    alt cloud route
      R->>M: HTTPS with the person's own key (keys_server, never in the agent)
      M-->>R: answer or tool calls
    else local route
      R->>G: HTTP /wake with the stack's token (Wake-on-LAN if asleep)
      G-->>R: local LLM answer, then /done (lease released)
    end
    R-->>H: answer or tool calls
    loop each tool call (one model round trip each)
      H->>H: tool: gateway CLI, terminal, browser, files in /workdir
    end
    H->>WV: sendMessage (Bot API)
    WV->>TG: delivered
    TG-->>P: answer
  end
  Note over DH,H: telemetry every 5 min (counts only), waker idle rule 10 min
  DH->>H: stop the brain when idle (no person, no busy job)
  DH->>DH: host suspends itself when every stack sleeps
```

The web chat takes the same route from Hermes on (Open WebUI → Hermes api_server → router), without the Telegram and Bot API steps;
the nginx in front of it stays up and starts the stack the same way.

## 2. API integrations by purpose

The `gateway` command is the single door from an agent to everything outside its container. Its verbs are grouped here by what they are for.
A key marked "own key" is the person's own free key, kept in that person's stack; the operator provides none (an optional key never blocks a verb:
each one falls back to a keyless source or says what is missing).

```mermaid
flowchart LR
  GW["gateway facade"]
  subgraph SW["Search and web"]
    SW1["web search and page fetch: Hermes backend, keyless"]
    SW2["dato wiki and noticias: Wikipedia, outlet RSS feeds"]
    SW3["dato dolar, economia, feriados: dolarapi, Bluelytics, argentinadatos, Nager.Date"]
    SW4["dato pelis: TMDB (own key), else Wikipedia"]
    SW5["job portals: jobfinder and the daily check"]
  end
  subgraph MV["Media and video"]
    MV1["transcode: GPU NVENC host, else local ffmpeg"]
    MV2["upscale: GPU 4x host only"]
    MV6["mosh: datamosh with FFglitch on a mosh host (CPU), no local fallback"]
    MV5["image: text to image on the GPU host, one picture at a time (v0)"]
    MV3["video: frames, audio and the LLM in one call"]
    MV4["qr: zxing-cpp, WeChat QR, zbar (local)"]
  end
  subgraph FS["Files and security"]
    FS1["bajar: yt-dlp (~1800 sites), aria2c for files and magnets"]
    FS2["virus: CIRCL hashlookup, no key, hash only"]
    FS3["virus: MalwareBazaar (own abuse.ch key), hash only"]
    FS4["virus --deep: ClamAV in a no-network container, file queue"]
    FS5["web publicar: git push, webhook, Pages, live check"]
  end
  subgraph MT["Maps and travel"]
    MT1["mapa buscar: Geoapify (own key), else Photon, Nominatim"]
    MT2["mapa cerca: Overpass, two endpoints"]
    MT3["mapa ruta: OSRM (FOSSGIS), transit as a Google Maps link"]
    MT4["map pictures: OSM tiles, or CARTO (own key)"]
    MT5["dato clima: Open-Meteo, ECMWF, GFS, air quality"]
    MT6["dato aviones: adsb.lol, else adsb.fi"]
  end
  subgraph IM["Infra and monitoring"]
    IM1["zabbix: read-only API token"]
    IM2["proxmox: PVE API, audit token, GET only, pinned certificate"]
    IM3["claude: Claude Code over an SSH gate"]
    IM4["Zabbix webhook, ops bot, Telegram alerts"]
    IM5["provider status monitor: public status pages"]
  end
  subgraph MS["Models and speech"]
    MS1["NVIDIA NIM"]
    MS2["Token Harbor (free allowance, class C)"]
    MS3["Gemini (paid, last resort)"]
    MS4["OpenRouter free, Hugging Face (fallback catalog)"]
    MS5["Cloudflare Workers AI (text off by default)"]
    MS6["local Gemma on the GPU host (first when up)"]
    MS7["Groq speech to text (own key)"]
    MS8["GPU STT and TTS: faster-whisper, Piper, Chatterbox"]
    MS9["Edge TTS (cloud, only when no host answers)"]
  end

  GW --> SW
  GW --> MV
  GW --> FS
  GW --> MT
  GW --> IM
  GW --> MS

  classDef live fill:#e8f1ff,stroke:#2b5fb4,color:#111;
  classDef ext fill:#f1f1f1,stroke:#555,color:#111;
  class GW live;
  class SW1,SW2,SW3,SW4,SW5,FS1,FS2,FS3,MT1,MT2,MT3,MT4,MT5,MT6,IM1,IM2,IM5,MS1,MS2,MS3,MS4,MS5,MS7,MS9 ext;
  class MV1,MV2,MV3,MV4,MV5,FS4,FS5,IM3,IM4,MS6,MS8 live;
```

Notes for this view:
- `virus` sends only a SHA-256, and only for executables, installers, scripts and archives; a document or photo is never looked up.
  `--deep` never sends the file anywhere: a host service scans it in a container with no network.
- Two sources are fallbacks by design: `transcode` falls back to local ffmpeg (CPU) if no GPU host answers; `speak` falls back to Edge only when no TTS host answers.
  Speech never runs on the VM's CPU, and `upscale` has no CPU fallback.
- Cloudflare Workers AI is reserved for images (by policy): a text request goes there only if `ROUTER_CLOUDFLARE_TEXT=1` is set.
  Text to image runs as the image service on a GPU host; the broker, quotas and per-person binding are still a design (section 4).

## 3. MCP integrations and their guards

Every MCP server today runs on the GPU workstation and is reached over SSH with a key that can do one thing: the forced command. The Hermes boot
step disables an SSH-based MCP entry while its host is unreachable and re-enables it on a boot that finds the host up. Only one stack has this
wiring in the repo (the stack template passes no MCP host to the other stacks).

```mermaid
flowchart LR
  subgraph CLI["Hermes clients on the VM"]
    C1["one stack: Resolve and EffectCraft entries"]
    C2["other stacks: no MCP wiring in the template"]
    C3["boot check: entry off while the host is unreachable"]
  end
  K1["MCP-only SSH key: forced command, nothing else"]
  subgraph WSN["GPU workstation"]
    D["mcp_dispatch.sh: picks the server by the command sent"]
    EC["EffectCraft headless MCP (27 tools measured)"]
    ECG["guard: reads only the input folder, writes only the output folder, refuses other paths and scripts"]
    RC["community Resolve MCP (37 tools)"]
    FL["mcp_filter.py: hides run_script_unsafe, fails closed"]
    RV["vendor ResolveMCP (after the filter)"]
    XV["Resolve -nogui on a private Xvfb: shared session, last client out quits it"]
  end
  subgraph HCS["Hostcare (pilot, not deployed)"]
    HB["ops brain: its own stack, no person data"]
    HK1["care key: level 0 read, level 1 known fixes (trust full)"]
    HK2["exec key: level 2 run(command, reason) (trust untrusted, operator approves)"]
    HM["hostcare_mcp.py on each machine (stdlib, forced command)"]
    HN["NEVER list on the host: secrets, access, firewall, deleting data, power"]
    HBL["blocker: no container reaches the VM's tcp/22"]
  end
  CG["claude-gate: same SSH pattern, not MCP. Claude Code limited to one folder, shell, web and MCP off"]
  subgraph PLN["Planned or considered"]
    P1["mcp_filter allow-list mode (new tools denied by default)"]
    P2["Craft family MCPs: PhotoCraft, MaterialCraft, TextureCraft pilots, behind allow-lists and the GPU lease"]
    P3["official Adobe remote MCP: not decided, disabled"]
    P4["Adobe guard: tools.include allow-list, trust untrusted, tiers 0 to 2"]
    P5["comfy-mcp: dropped until every tool takes the lease"]
    P6["Hermes optional-mcps and A2A: considered"]
  end
  subgraph NO["Refused by design"]
    N1["Blender MCPs: execute_blender_code is arbitrary Python"]
    N2["community Adobe and Substance MCPs: script surfaces"]
    N3["Comfy Cloud MCP and VirusTotal MCP: break the own-key and privacy policy"]
  end

  C1 ==>|"ssh"| K1
  C3 -.-> C1
  K1 ==> D
  D ==>|"effectcraft"| EC
  EC --- ECG
  D -->|"default"| RC
  D ==>|"davinci-native"| FL
  FL ==> RV
  RC --> XV
  RV --> XV
  HB -.->|"ssh, care key"| HK1
  HB -.->|"ssh, exec key"| HK2
  HK1 -.-> HM
  HK2 -.-> HM
  HM -.-> HN
  HBL -.-> HB
  P1 -.-> FL
  P2 -.-> D
  P3 -.-> P4
  P5 -.-> P1

  classDef live fill:#e8f1ff,stroke:#2b5fb4,color:#111;
  classDef mcp fill:#e4f6e8,stroke:#1b7a3a,color:#111,stroke-width:3px;
  classDef planned fill:#fff4d6,stroke:#b07800,color:#111,stroke-dasharray: 5 5;
  classDef refused fill:#fde8e8,stroke:#a02020,color:#111;
  class C1,C2,C3,K1,D,ECG,FL,XV,CG live;
  class EC,RC,RV mcp;
  class HB,HK1,HK2,HM,HN,HBL,P1,P2,P3,P4,P5,P6 planned;
  class N1,N2,N3 refused;
```

Notes for this view:
- The community Resolve server has no action that takes caller-supplied code, so it runs unfiltered. The vendor server has `run_script_unsafe`
  (full filesystem, network and subprocess access as the machine's user), which would be a shell behind the MCP-only key, so the filter removes it from
  `tools/list` and refuses a `tools/call` for it. The filter fails closed: batches, junk lines and non-string tool names never reach the server.
- `gpu-host/mcp_dispatch.sh` is the source of the live dispatcher: an `effectcraft` case, a `davinci-native` case (the vendor server through the filter)
  and a default case that starts the community Resolve wrapper. Both Resolve routes run the `-nogui` backends by default (an environment override selects the GUI ones; `aibridge/VIDEO_TOOLS.md`).
- Hostcare levels: 0 read and 1 known fixes need no approval, 2 asks the operator first, and "never" is enforced on the host even after approval.
  Client machines would get level 0 only.
- Token Harbor is not an MCP server: it is an OpenAI-compatible model provider (section 2).

### 3.1 A vendor's MCP server or our own gateway command

More vendors now offer a hosted MCP server next to their API. The vendor's MCP server is not always the better integration.
Often a `gateway` subcommand that calls the plain API is better. Decide with these questions, in this order:

1. **What leaves, and can we bound it?** A gateway command sends only what we cut (an excerpt, a re-encoded photo with no
   metadata, one field) and says so. An MCP tool takes whatever the model passes, and some take only a public URL, so the file
   would first have to be put on the internet.
2. **How much power does the connection carry?** Vendor MCP servers are built for an assistant managing an account. Their grants
   often include billing, payment links and token rotation next to the one useful call. A person's bot that anyone can message
   must hold only the one call it needs. That is a per-person API key used by one command.
3. **Whose key, and how is it stored?** Our rule is each person's own key, checked with a real call and kept in their stack's
   `.env` (the `SERVICES` table, `gateway servicios guardar`). An OAuth connector per person adds a browser flow, refresh tokens
   and a revocation story for every stack.
4. **What does the model see?** A gateway command prints fixed sentences, sanitises external text and keeps keys and content out
   of logs. An MCP tool returns the vendor's raw answer into the conversation. That answer is untrusted text that then travels
   to the cloud model.
5. **Does the vendor itself recommend the API for programmatic use?** Many do: their MCP server is for interactive use by a person
   in an assistant.

Use the vendor's MCP server when the work is interactive and broad (many tools, no fixed shape), it runs under the operator's own
account, and its tools can be filtered (section 3 guards). Write a gateway command when the job is one narrow call made on a person's
behalf.

| Vendor | Their MCP server | Our choice | Why |
|---|---|---|---|
| AudD (song recognition, 2026-11-09; retired) | `https://mcp.audd.io`: OAuth 2.0 with PKCE; tools for API requests, docs, profile, usage, token get/rotate, plans, billing and Stripe payment links. Audio only by URL ("binary file upload is not possible through the tool"). | It was `gateway song FILE [--at S]` on the HTTP API with the person's own `api_token`: a 12 s mono excerpt (hard cap 15 s) uploaded directly, token and file in the POST body, never in the URL; ACRCloud as the fallback. **No longer offered**: `gateway song` now uses ACRCloud only, so the skill index, the service card and the code are one provider smaller. | The audio would have to be published to reach the MCP tool, and the grant carries billing and token rotation; AudD's docs recommend the direct API for programmatic recognition. It worked as designed. **To bring it back:** the last commit that holds the full implementation and its selftest is `3e76793` (`aibridge/gateway.py` `audd_recognize`, the `audd` entry of `SERVICES`, `aibridge/gateway_song_selftest.py`, the skill text of that commit): `git show 3e76793:aibridge/gateway.py`. A token that a person saved earlier stays in their stack's `.env` as `AUDD_API_TOKEN`; it is ignored and never sent, and there is no command to remove it any more (edit the file by hand if it matters). |
| Comfy Cloud, VirusTotal | hosted MCP | refused (section 3) | Breaks the own-key and privacy rules. |

## 4. Planned and not built

Built today: host choice by expected finish time for media jobs (`ranked()` in `gateway.py`, each GPU service answers `GET /status`), and
`gateway maquina` for remote machines with credit (`MACHINES.md`). File exchange between agents of a pool and GPU job inputs/outputs through a small
S3 store is a design (`BLOB_STORAGE.md`).

Still design only, listed in the "Open design" section of `GPU_MEDIA_TOOLS.md`: a pool broker with per-stack quotas, a GPU lease and an operator busy
switch, host heartbeats, a warm worker with identity binding, Blender fixed-argv jobs, CAD from code, allow-listed Craft-family MCPs, and an optional
Adobe connector. Rules that shape those designs:
- AV1 is the only job class allowed a CPU path, always with an ETA the person sees. Images, 3D renders, upscaling, speech to text and text to speech never
  run on a CPU fallback; they fail clearly instead.
- Heartbeats are hints, not trust: each host has its own token, the privacy class of a host is fixed in the operator's config (never in the heartbeat),
  and a person's job never lands on a machine the person did not agree to.
- A person's photos and `.blend` files never leave the GPU host; a third-party connector may receive a file only with the person's own account and a yes for each file.
Remote desktop and game streaming, evaluated in November 2026 for a GPU host that is powered on and suspended on demand:
- Sunshine with Moonlight is the low-latency path (the card's hardware encoder, H.264 and HEVC; no AV1 on the RTX 3060 Ti). It has no NAT traversal, so a
  person outside the LAN needs a VPN. The project's repository moved from the `LizardByte` to the `SunshineStream` organisation (same repository id, same
  maintainer): check such a move before installing a package from it. Releases are daily builds marked as prereleases; the stable ones are a few months apart.
  Newer versions need a `pairing_id` besides the PIN: the pending requests are listed by `GET /api/pin`.
- Steam in a container (Steam-Headless, Wolf, linuxserver/steam) works, but needs unconfined seccomp and extra capabilities (Wolf also needs the Docker socket,
  which is root on the host), so none of them is an isolation boundary. Steam accounts are personal under the Subscriber Agreement (last updated 2026-09-10):
  no sharing, no renting. Native on the host with the operator's own account is the proof of concept; a container per person waits for that question.
- What was set up and measured on the host, and what breaks (audio sink, the absolute pointer read as a joystick, `libudev.so.0` for old native games,
  frame limiter and post-process AA layers, display refresh): `gpu-host/remote-desktop/REMOTE_DESKTOP.md`.
- Considered and not adopted: Parsec (closed, account-bound, not automatable), GPU passthrough to a VM on a single-GPU host (the host loses its only GPU).
- New image models that fit 8 GB (Anima 2B, Mage-Flow turbo, FLUX.3 Klein) are for the operator's own testing: Anima's licence is non-commercial and counts
  serving other people as commercial, Mage-Flow's repository says research use only, and FLUX.3 Klein is gated. FLUX.2 klein 4B and Z-Image Turbo
  (both Apache-2.0) stay the tiers for other people.
- Considered upstream and not adopted for now: A2A as a base for hostcare, the optional `comfy-cloud` MCP (rejected), upstream image and video plugin slots
  (to plug a design into later). See `HERMES_UPSTREAM_SCAN.md`.

## Free image APIs checked

Checked against official pages and the account's own model catalog (late 2026-11), so re-check before relying on any number:
- **Cloudflare Workers AI is the only viable free route.** Text-to-image models include `flux-1-schnell`, `flux-2-klein-4b`, `stable-diffusion-xl-lightning`; `flux-2-klein-4b` takes an input image. Free allowance: 10,000 Neurons a day, reset 00:00 UTC, no overage billing. It is shared by everything on the account, so keep a per-person daily budget in the gateway and send it no chat text. Enforcement is loose: the dashboard, not the router's own count, is the truth. Privacy class A (see `DATA_LAW_AND_KEYS.md`).
- **Not viable:** Gemini API image/video (no free tier found), Hugging Face Inference Providers (no free credits), NVIDIA's hosted catalog (no image models listed), consumer web apps with daily credits (no API to give a person).
- **Video:** no free API with a renewing allowance exists. Video runs on a local GPU host (`GPU_MEDIA_TOOLS.md`).
- **Choosing the best model per task** is measured the way `ops/model_scores.py` ranks text models: a fixed prompt set and a vision-model score, minus a cost term.

## Integration inventory

Auth values: "none" needs no key; "own key" is the person's own key, optional unless stated; "operator-owned" is a credential held by the operator for
operator infrastructure (never lent to a person).

| Integration | Kind | Where it runs | Auth | Status | Source file |
|---|---|---|---|---|---|
| NVIDIA NIM chat models | API | cloud, called by the router in each stack | own key | live | `aibridge/router.py`, `aibridge/ops/lib/providers.py` |
| Token Harbor (OpenAI-compatible, free allowance) | API | cloud, called by the router | own key (opt-in, privacy class C) | live | `aibridge/router.py`, `aibridge/ops/lib/providers.py` |
| Google Gemini (paid, last resort) | API | cloud, called by the router | own key | live | `aibridge/router.py`, `aibridge/ops/lib/providers.py` |
| OpenRouter free models | API | cloud, fallback catalog and menu probes | own key | live | `aibridge/ops/lib/providers.py`, `aibridge/ops/model_guard.py` |
| Hugging Face router | API | cloud, fallback catalog | own key | live (catalog entry; a key is optional) | `aibridge/ops/lib/providers.py` |
| Cloudflare Workers AI (text) | API | cloud, one stack only, explore candidates | operator-owned | live but off for text unless `ROUTER_CLOUDFLARE_TEXT=1` | `aibridge/router.py` |
| Cloudflare Workers AI (images) | API | cloud | operator-owned | planned (see "Free image APIs checked" below) | `aibridge/INTEGRATIONS_MAP.md` |
| Local Gemma 4 E4B (llama.cpp, OpenAI-compatible) | service | GPU workstation, port 8630 | none | on demand | `llm/Dockerfile`, `gpu-host/run_services.sh` |
| Local-first router with consent and cloud-direct switch | service | inside every stack container | n/a | live | `aibridge/router.py`, `aibridge/ops/gateways.json.example` |
| GPU transcoder (NVENC, closed option list) | service | GPU workstation, port 8610 | optional bearer token | on demand | `transcoder/server.py`, `aibridge/gateway.py` |
| GPU upscaler (4x) | service | GPU workstation, port 8600 | optional bearer token | on demand | `upscaler/server.py`, `aibridge/gateway.py` |
| Mosher (datamosh, FFglitch, CPU only) | service | any Docker machine (GPU workstation or the VM), port 8690 | bearer token (required) | on demand | `gpu-host/mosher/server.py`, `aibridge/gateway.py` (`cmd_mosh`) |
| GPU speech to text (faster-whisper) | service | GPU workstation, port 8620 | none | on demand | `stt/server.py`, `aibridge/gateway.py` |
| GPU text to speech (Piper, Chatterbox) | service | GPU workstation, ports 8640 and 8650 | none | on demand | `tts/server_piper.py`, `tts/server_chatterbox.py`, `gpu-host/run_services.sh` |
| Voice proxy (OpenAI-compatible STT and TTS) | service | per-stack container | none | live | `stt/proxy.py`, `aibridge/stacks/docker-compose.stack.yml` |
| Groq speech to text (voice notes fallback) | API | cloud | own key | live | `aibridge/gateway.py` (`cmd_transcribe`, `SERVICES`) |
| Edge TTS (cloud fallback) | CLI | inside the stack container | none | live | `aibridge/gateway.py` (`cmd_speak`) |
| Hermes web search and page fetch (Keenable backend) | API | cloud, Hermes tool | none | live | `aibridge/start_hermes.sh` |
| `gateway dato wiki` (Wikipedia) | API | cloud | none | live | `aibridge/gateway.py` |
| `gateway dato noticias` (outlet RSS feeds) | API | cloud | none | live | `aibridge/gateway.py` |
| `gateway dato dolar`, `economia` (dolarapi, Bluelytics, argentinadatos) | API | cloud | none | live | `aibridge/gateway.py` |
| `gateway dato feriados` (argentinadatos, Nager.Date) | API | cloud | none | live | `aibridge/gateway.py` |
| `gateway dato pelis` (TMDB) | API | cloud | own key (optional) | live | `aibridge/gateway.py` (`SERVICES`) |
| `gateway dato clima` (Open-Meteo, ECMWF and GFS side by side, air quality) | API | cloud | none | live | `aibridge/gateway.py` |
| `gateway dato aviones` (adsb.lol, adsb.fi) | API | cloud | none | live | `aibridge/gateway.py` |
| `gateway mapa buscar` (Geoapify, else Photon, Nominatim) | API | cloud | own key (optional) | live | `aibridge/gateway.py` (`SERVICES`) |
| `gateway mapa cerca` (Overpass) | API | cloud | none | live | `aibridge/gateway.py` |
| `gateway mapa ruta` (OSRM by FOSSGIS; transit as a Google Maps link) | API | cloud | none | live | `aibridge/gateway.py` |
| Map pictures (OSM tiles, or CARTO basemaps) | API | cloud | none, or own key for CARTO | live | `aibridge/gateway.py` |
| `gateway bajar` (yt-dlp, aria2c) | CLI | inside the stack container | none | live | `aibridge/gateway.py`, `aibridge/ops/yt-dlp.conf` |
| Subtitle backlog fetch | CLI | inside the stack container or hub | none | live | `aibridge/subs_fetch.py` |
| Job portals and the daily check | CLI | inside the stack container | none | live (notices are opt-in per person) | `aibridge/jobpush.py`, `aibridge/buscar-empleos.cjs` |
| `gateway qr` (zxing-cpp, WeChat QR, zbar) | CLI | inside the stack container | none | live | `aibridge/gateway.py` |
| `gateway video`, `bench`, `status`, `estado` | CLI | inside the stack container, call GPU hosts | none | live | `aibridge/gateway.py` |
| `gateway virus`: CIRCL hashlookup | API | cloud | none | live | `aibridge/gateway.py` |
| `gateway virus`: MalwareBazaar (abuse.ch) | API | cloud | own key (optional) | live | `aibridge/gateway.py`, `aibridge/skill_packs.json` |
| `gateway virus --deep`: ClamAV scan service | service (file queue) | VM host plus a throwaway no-network container | none | built, first run by the operator | `aibridge/ops/scan/scanner.py`, `aibridge/CAPABILITIES.md` |
| `gateway zabbix` | API | monitoring server | operator-owned read-only token per stack | live | `aibridge/gateway.py`, `aibridge/ops/ZABBIX.md` |
| `gateway proxmox` (PVE API, GET only, pinned certificate) | API | Proxmox hosts | operator-owned audit token | live | `aibridge/gateway.py`, `aibridge/SKILL_proxmox.md` |
| `gateway web` (git push, deploy webhook, Pages) | CLI | stack container, deploy key for one repo | own deploy key | live on one person stack | `aibridge/gateway.py`, `aibridge/SKILL_website.md` |
| `gateway claude` (claude-gate) | CLI over SSH forced command | a machine where Claude Code is logged in | own login on that machine | live | `aibridge/ops/install_claude_gate.sh`, `aibridge/ops/SKILL_claude_remote.md` |
| Telegram Bot API (one bot per person) | API | cloud, polled by Hermes | own bot token | live | `aibridge/start_hermes.sh`, `aibridge/ops/stack_telegram.py` |
| Local Telegram Bot API server (large files) | service | VM container | operator-owned app id | live where configured | `aibridge/docker-compose.yml`, `aibridge/patches/telegram_large_files.py` |
| Open WebUI web chat | service | per-stack container | per-person login | live | `aibridge/stacks/docker-compose.stack.yml`, `aibridge/ops/openwebui_setup.sh` |
| Ops bot (alerts and operator chat) | API | VM host | operator-owned bot | live | `aibridge/ops/opschat.py`, `aibridge/ops/lib/notify.py` |
| Zabbix webhook receiver | service | VM host | shared token header, operator-owned | live | `aibridge/ops/zabbix_hook.py`, `aibridge/ops/zabbix/provision.py` |
| Hub collector (feeds, read-only per person) | service | VM container run by a timer | none | live on one stack | `aibridge/hub/HUB.md`, `aibridge/hub/hub.py` |
| Waker (sleep and wake, RAM guard) | service | VM host | n/a | live | `aibridge/ops/wake/waker.py` |
| Backup, telemetry, key and model guards, provider status monitor | service | VM host timers | operator-owned | live | `aibridge/ops/backup-stacks.sh`, `aibridge/ops/telemetry.py`, `aibridge/ops/model_guard.py`, `aibridge/ops/provider_status.py`, `aibridge/ops/provider_uptime.py` |
| MCP: DaVinci Resolve, community server | MCP | GPU workstation, over SSH | none (key restricted) | live on one stack | `gpu-host/mcp_dispatch.sh`, `aibridge/ops/resolve_host/README.md` |
| MCP: DaVinci Resolve, vendor server behind `mcp_filter.py` | MCP | GPU workstation, over SSH | none (key restricted) | live on one stack | `aibridge/ops/resolve_host/mcp_filter.py`, `aibridge/VIDEO_TOOLS.md` |
| MCP: EffectCraft headless | MCP | GPU workstation, over SSH | none (key restricted, confined folders) | live on one stack | `gpu-host/mcp_dispatch.sh`, `aibridge/SKILL_effectcraft.md` |
| MCP: hostcare (per machine) and the ops brain | MCP | each host over SSH; brain in its own stack | operator-owned keys | pilot (built and tested, blocked on the network path) | `aibridge/ops/hostcare/hostcare_mcp.py`, `aibridge/ops/hostcare/HOSTCARE.md` |
| `mcp_filter.py` allow-list mode | MCP guard | GPU workstation | n/a | planned | `aibridge/GPU_MEDIA_TOOLS.md` |
| Machine-power provider (sibling project): `gateway maquina`, `/machine` | API | the sibling project | the person's own account on the provider | live where configured | `aibridge/MACHINES.md`, `aibridge/gateway.py` |
| A person's own game PC: `gateway lugar`, `/lugar` (run a game by name, shader phase, freeze, switch off) | HTTP to the GPU gate's `/host/*` | the GPU host (gate + `host_control.py`) | its own `GATE_HOST_TOKEN` (never the stacks' gate token), kept in the stack's `lugares` block | live where configured (stand-in for the rental panel's Linux agent) | `aibridge/LUGAR.md`, `gpu-host/gate/host_control.py` |
| Image service (`gateway image`, text to image, SDXL-Lightning) | service | GPU host, port 8660, ComfyUI inside the container only | bearer token | live (one picture at a time, model unloaded after 60 s idle) | `gpu-host/imggen/server.py`, `aibridge/gateway.py` |
| Sunshine host and Moonlight client (low-latency remote desktop, H.264/HEVC through the GPU's encoder) | service | GPU host, native, as a user systemd unit; the client runs on the person's own PC | per-client pairing PIN; web admin login held by the operator | pilot (paired and used on one host) | `aibridge/gateway.py` (`maquina entrar`, access kind `moonlight`), `aibridge/MACHINES.md` |
| PipeWire with a virtual sink for the remote desktop's audio (the host has no sound card) | service | GPU host, user session | none | live on one host | `gpu-host/remote-desktop/REMOTE_DESKTOP.md` |
| MangoHud (frame limit without vsync) and vkBasalt (SMAA/FXAA/CAS), Vulkan layers from Debian | library | GPU host, per game through the Steam launch options | none | live on one host (limit measured; AA effect not measured) | `gpu-host/remote-desktop/REMOTE_DESKTOP.md` |
| Browser desktop in a container (Selkies-based webtop image) | service | GPU host, one container per person, LAN address only | per-container login | pilot (no GPU yet, one container) | this file |
| Machine-power provider agent for Linux (heartbeat, reservation queue that launches Steam titles, library inventory, screens, preview frames) | service | on the reserved machine, as a user systemd unit | none beyond the hub address | built by the sibling project; to be reinstalled on a rebuilt host | the sibling project's Linux agent script (kept in its own repository) |
| Steam client (Proton), native on the GPU host | CLI and desktop app | GPU host, the operator's own account only | own account | pilot (proof of concept; the Steam terms make the account personal) | this file |
| Epic Games Launcher Preview for Linux (native, from October 2026) and Heroic with Legendary | desktop app | GPU host | own account | considered (the Preview page was not readable from automation; Heroic is the open alternative) | this file |
| EffectCraft headless in a locked-down container (no network, read-only root, folders confined by `--automation-read-root` and `--automation-write-root`) | MCP over stdio inside the container | any Docker host, CPU rendering | none | built and tested on one host | `gpu-host/effectcraft/Dockerfile` |
| NVIDIA CUDA package repository for Debian 13 (driver pin plus `nvidia-open`) and NVIDIA Container Toolkit repository | package source | GPU hosts, installed by the operator | none (signing keys checked before use) | live | `gpu-host/upkeep/UPKEEP.md` |
| ComfyUI v0.46.0 with PyTorch 2.14.1 (CUDA 13 wheels) behind the image service | service | GPU host container, port 8660 on loopback | bearer token | pilot (the three proven tiers are re-measured on it) | `gpu-host/imggen/server.py` |
| GPU host sleep observer (suspend to RAM when nothing needs the host; wake-on-LAN brings it back in about 10 s) | service | each GPU host, systemd timer | none (reads the gate's token from the host's private settings) | built and tested on one host | `gpu-host/sleep/README.md` |
| Hermes upstream: A2A, optional-mcps, `tool_costs` and `spend_limit` | MCP and API | Hermes | n/a | considered | `aibridge/HERMES_UPSTREAM_SCAN.md` |
| Rejected: Blender MCPs, Comfy Cloud MCP, VirusTotal MCP, community Adobe and Substance MCPs | MCP | n/a | n/a | rejected | `aibridge/GPU_MEDIA_TOOLS.md`, `aibridge/HERMES_UPSTREAM_SCAN.md` |
