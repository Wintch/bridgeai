---
title: Software and data access for AI agents (install control, egress, access levels)
scope: AI-agent containers that run shell commands for a person or a business, on a host the operator controls; installs, outbound data, and which files an agent may see
when_to_use: an agent can install software or reach the internet freely; designing a package gateway; deciding what an agent may read, send or keep; a person asks to protect a private project or confidential code; choosing between an allow list, a sandbox and an outside watcher
related: [README.md, policies.md, containers-and-images.md, detection-and-audit.md, firewall-and-ports.md, ../KEY_SECURITY.md, ../DATA_LAW_AND_KEYS.md, ../SECURITY_WATCH.md]
---
# Software and data access for AI agents

Status: design. Nothing here is a finished control yet. Each part says what is built and what is only proposed. Numbers marked **(est.)** are estimates.

An agent that runs shell commands is a user with a keyboard and no judgment. This doc covers two questions. First, how does software get onto the agent's machine, and who decides? Second, what data can the agent see, and how can that data leave? The honest answer to the second one is harder than the first.

## The problem

A typical agent container looks like this:

- The agent runs as **root** inside its container. A `sudo` binary may be present; as root it blocks nothing.
- It can run `apt`, `pip`, `npm` and `git clone`. The base Python is protected by PEP 668, but `--break-system-packages` skips that protection.
- Outbound traffic is open to the internet on every port and protocol. The firewall blocks the LAN, the host and other stacks, but not the outside world.
- DNS is an open and unlogged channel (resolver, external port 53, and DNS over HTTPS on 443).
- The terminal runs in the same container as the agent. There is no inner sandbox.
- The approval gate is a list of regex patterns for dangerous commands. It looks at deletions, `curl | sh`, writes to config and uploads with secrets in the body. It does **not** look at installs, `git clone`, `scp`, `rsync`, `nc`, `rclone`, `git push` or `curl -d @file`.
- The only rule against installing is a paragraph in the agent's instructions. That is advice, not a control.
- The agent's own framework may install things lazily. Turn that off.
- A package scanner may have been removed from the image. If so, nothing inspects packages.

So one chat message can make a root process run any command. A short list of destructive patterns asks first. Installing code and sending files to any host does not ask.

A healthy path must exist too. If the image has no `python3-venv` and no `uv`, the instruction "use a venv" cannot work. That pushes the agent toward `--break-system-packages` **(inferred from structure, not tested)**. Fix the cause before adding a ban.

### What actually leaks data

The real channels are wider than "uploads":

| Channel | Why it is hard to close |
|---|---|
| Any network tool (`curl`, `wget`, `git`, `ssh`, `nc`, a Python socket) | The agent can write its own tool in one line. |
| URL query strings | `GET https://host/?d=<data>` looks like a normal page load. |
| DNS | Data fits in host names. Open resolver, no log. |
| Messaging tokens | If the agent can read the bot token, it can send files to any chat the bot knows. The messaging API host must stay allowed because the bot needs it, so egress rules cannot close this. Keep the token out of the agent's environment and files; send through a gateway verb. |
| Any allowed host | Code hosts, CDNs and file hosts accept uploads. Without TLS interception there is no size or content limit. |
| **The model provider** | Everything the model reads goes to the provider. Every allow list includes the model endpoint. No egress control covers this. |

The last row decides the design. At the default level, the provider receives whatever the agent reads. Only a local model, or a provider under contract, changes that.

## The lethal trifecta

Three things together make leaks easy:

1. Access to private data.
2. Exposure to untrusted content (web pages, files, messages from strangers).
3. A way to communicate outward.

**Rule:** remove one leg per stack. Guardrails that "catch 95%" are not enough, because the attacker needs only one miss.

| Mode | Private data | Untrusted content | Outbound |
|---|---|---|---|
| Open (bots that work on public data) | No | Yes | Yes |
| Personal (L1) | Yes | Only through a gateway that summarizes with a no-tools call | Domain allow list, no arbitrary outbound |
| Vault (L3) | Yes | **No** (no web, no files or senders from strangers) | **Only the model endpoint** |

Cheap additions:

- The web gateway refuses URLs with a query string. The agent framework may already refuse URLs that carry secrets. That guard matches secret patterns, not arbitrary private data, and it covers only the framework's web tools, not `curl` in the terminal. Treat the query-string rule as a complement and test what the existing guard detects.
- Untrusted content is read by a summarizer with no tools. Only the summary reaches the main agent.

## The software gateway

The same idea as the web-search gateway: the agent asks for a capability, and the host decides how and from where. The agent no longer installs anything itself.

### Flow

```
agent: gateway pkg request <name>
  -> look up the catalog (a file in the repo)
     -> in the catalog and allowed for this kind of bot -> install
     -> not in the catalog -> "not allowed; I asked the operator"
                              + a ticket to the operator's ops bot, with a one-line reason
  -> install by source type (table below)
  -> log: name, version, hash, who, when
```

The "refuse first, then a person approves" pattern comes from artifact-repository managers. No standard "install broker" product exists, so build it.

### Sources

| Source | How | Where it lives | Check |
|---|---|---|---|
| Debian stable and its security repository | Baked into the image (the common case), or an approved package | The image. A package installed at runtime disappears when the container is recreated. | Debian origin. Security updates arrive on rebuild. |
| PyPI | Wheels only (`--only-binary :all:`), pinned version, `--require-hashes`, wait 24 to 72 hours after publication | A per-workspace venv, never the system Python | A vulnerability audit (pip-audit or OSV). **Proposed.** |
| npm | Pinned version and a lockfile | The person's tools directory | Lockfile audit |
| Large third-party binaries | Only through the gateway, with a size limit and a checksum | A documented tools directory, excluded from backups | SHA-256 stored in the catalog |
| Anything else (`git+URL`, third-party apt repos, `curl \| sh`) | **No.** It becomes a request to a human. | n/a | n/a |

### Who gets what

| Kind of bot | Policy |
|---|---|
| Business bots | Only what the image ships. `gateway pkg` answers "ask the operator". Refusing costs nothing, because these bots never needed installs. |
| Personal bots | Approved catalog, a venv per person, everything logged. |
| Power-user bot | Catalog, plus a phone approval for each install outside the catalog. Same log. |

### What the bot is told

The bot's instructions must match reality, or the bot works around the block. Short text:

> Do not install anything yourself. If a tool is missing, run `gateway pkg request NAME`. If it is on the list, it installs. If not, I tell the operator and say how long it may take. For Python libraries use `uv venv /workdir/venvs/NAME` or the path the gateway gives. `apt`, `dpkg`, `sudo`, `pip --break-system-packages`, `curl | sh` and third-party repos are blocked, so do not try. If a block stops you, say so.

The skill needs one tested venv command. When a command is missing and the right answer is another gateway (for example the host-care gateway instead of Docker inside the container), the refusal names that gateway. A wrong install is not the answer to "command not found".

### Keeping it current

- Rebuild images on a schedule **(proposed: weekly)** and scan them. Report counts only.
- The catalog is versioned in the repo. Each entry carries a version, a hash and the allowed bot kinds.
- A nightly read-only job in the ops bot counts missing commands and modules, installs by verb, venvs built for another Python version, and new executables in the workspace. It reads counts from session stores, never chat text. The counts feed the image backlog.
- A venv built for an older Python breaks when the image moves to a new one. Check each venv's `pyvenv.cfg` against the system Python at start and warn the person.

### What the image should ship

Ship what agents keep installing: the venv tooling (`python3-venv` and `uv`) first, then small utilities such as `jq`, `zip`, `yq`, `lsof`. Do not ship Docker, a compiler, `cron` (the framework has its own scheduler), or heavy numeric and ML libraries. Heavy libraries go in an on-demand venv requested through the gateway.

### Prerequisites

Set the framework's lazy-install switch to false. Make the framework's own code (including the approval gate) root-owned or read-only, so the agent cannot edit its own gate.

## Binary and behaviour controls

Linux equivalents of "ask before running a new program", compared for a small host where RAM is the limit.

| Option | What it gives | Fit | Verdict |
|---|---|---|---|
| Approval deny list (apt, apt-get, dpkg, sudo, `--break-system-packages`, `curl \| sh`, add-apt-repository) | Tells the agent no, early, and logs it | Matches the command string only. `python3 -c`, code execution and a script written to a file skip it. A seat belt, not a wall. | Do it, with a startup selftest that fails if a deny stops applying |
| `allow_lazy_installs=false` | Stops the framework installing on its own | Free | Do it |
| Drop `NET_RAW` | Removes raw sockets and sniffing | Business bots do not need it **(est.)** | Do it first |
| Remove `nmap` and `tcpdump` from stacks that do not need them | Fewer tools to misuse | Free | Do it |
| Read-only root filesystem, with tmpfs and volumes | Runtime installs go to a volume; framework code stops being editable | Try it on a guest stack first | Next phase |
| Custom seccomp | Blocks `ptrace`, `bpf`, `userfaultfd`, `mount`, `unshare`, `perf_event_open` | Default profile today | Next phase |
| Non-root user | The container's root stops owning the filesystem; fewer capabilities needed | The image is built around root's home | Large refactor. A separate project. |
| Custom AppArmor (derived from the default) | Denies exec from `/tmp` and the workspace, writes to `/usr` and `/opt` | Needs testing with ffmpeg, Python and Node | Strict profile only for vault mode |
| fapolicyd | The closest thing to AppLocker | Weak in containers: the dpkg backend is limited, it does not understand namespaces, and it misses Python imports | Do not adopt |
| Falco | Detects connections to unlisted hosts, new `nmap`/`ssh`/`nc` processes, writes to `/usr`, key-file reads. Alert only. | Runs on a current Debian. Overhead claims (1 to 5% CPU) are unverified. Measure for a week. | Alert-only phase |
| Tetragon | Also blocks (signal and override) | Container identity outside Kubernetes is unconfirmed; a bad policy breaks workloads | Only if enforcement is truly needed |
| Gateway plus controlled egress | The real enforcement. Without it the gateway is only convenient, because the agent can bypass it with `curl` or `pip`. | Low cost | The main control |

I do not recommend a per-binary allow list inside the container. The agent legitimately uses Python, Node, ffmpeg, curl and git. What can be enforced is **networks, mounts and custody of keys**.

Approvals also need two habits: never persist "always allow", and make the approval files unwritable by the agent.

## Egress as the central control

| Step | What | Effort |
|---|---|---|
| 1 | Firewall rules for the stacks' network: cut SMTP (25, 465, 587) and outbound SSH (22); keep 80/443 and the provider ports in use; UDP 53 only to the resolver; block UDP 443 (QUIC) | S |
| 2 | An outbound proxy with a log and a byte count per stack. A week in report mode first, then an allow list. | M |
| 3 | Our own DNS with a log and a rate limit | M |
| 4 | Per-project classes with different allow lists | M to L |

Test step 1 on a guest stack first. Closing external port 53 can break the container's DNS if the host's resolver changes. Restricting a stack that needs the hypervisor, a GPU host or tool servers to its own subnet needs a destination inventory first. These changes need root on the host, so a person with that access runs them.

## The outside watcher

A watcher that runs on the host, outside the container, is a good idea as **detection and a pause button**, not as the primary control. `docker pause` is a host action. The agent cannot stop it from inside.

### What it watches

Two stages, to keep the load low.

**Stage 0: no eBPF.** A timer on the host. Counts and names only.

| Signal | Source |
|---|---|
| New executables outside the venv directory | `docker diff` against a saved baseline |
| Changes in system paths (`/usr`, `/opt`, `/etc/apt`) | `docker diff` |
| Outbound bytes per stack | Firewall counters per subnet (more reliable than `docker stats`, which only counts a running container) |
| Die, OOM, exec | `docker events` |
| Venvs built for another Python version | Read `pyvenv.cfg` |

Keep the `docker diff` baseline per container and reset it when the container is recreated. A sleeping container keeps its layer, so the diff still works; a recreated one starts clean.

**Stage 1: Falco.** A few small container rules: a shell started by a non-interactive tool, a new connection to an unlisted destination, a new `nmap`/`ssh`/`scp`/`nc` process, a read of key files. Events go through a webhook relay to a small receiver on the host (about 30 lines **(est.)**).

### When it pauses

Pause only on high-confidence rules. Everything else is an alert.

| Rule | Action |
|---|---|
| A canary file (planted in a vault) is read or sent | Pause and alert |
| Outbound volume far above normal **together with** a new destination | Pause and alert |
| A big read of a private folder followed by a network call | Pause and alert |
| New executable outside the venv directory | Alert only |
| New destination with low volume | Alert only |

`docker pause` freezes the cgroup, keeps memory and can be undone (unlike kill). It interacts with the wake-on-demand waker: mark the stack as "paused by the guard" so the waker does not "fix" it by waking it. For a stack that is asleep the action is to block the wake, not to pause.

### How it alerts

- The **person**, through their messaging bot if they have one, with buttons: "resume" or "keep paused". The text says what was seen, in numbers, never chat content.
- The **operator**, through the ops bot with fixed fields, and through monitoring.
- No test messages through a person's bot. Night alerts go only to the operator unless a pause rule fired.

### Avoiding false alarms

1. Start with a week in **report** mode to learn the real hosts. Set thresholds afterwards.
2. Thresholds per stack, not global. A power user and a business bot have very different profiles.
3. Known destinations (the router's providers, the messaging API, the gateways) never alert.
4. Pause only on canary rules and signal combinations, never on one signal.
5. A silence is per stack and per rule, and it expires.

The pause is one more lever, with undo, in the list of actions the person consented to for early alerts and auto-repair.

## Data access levels

The person labels the **project**. The system does not guess from content. Privacy is decided by who and where, not by sniffing files.

| Level | What it is | The agent may | Data out | Models | Mechanism |
|---|---|---|---|---|---|
| **L0 Public** | Downloads, caches, public data, media meant to be shared | Everything | Free | Whatever the person already allows | Today's behaviour, plus quotas and cache cleanup |
| **L1 Personal** (default) | Chat, memory, general workspace | Read, write, delete (there is a backup) | Tools with counting | Provider classes with agreed terms; never a class with unacceptable terms | Owner-and-group-only file permissions instead of world-readable, strict media delivery from an outbox directory, encrypted backup with a copy off the host |
| **L2 Private project** | Code and assets the person owns or licenses | Read and write **only while the project is open** | Gateway commands that send bytes refuse the project path unless the person confirms | Class A or local. No pins, no explore mode. | A project directory with an access manifest, mounted **only while the project is active** (open and close commands; the stack is recreated, **about a minute or two (est.)** once). Its own backup lane: no size skip, short retention, a snapshot before each session. |
| **L3 Vault** | Confidential IP: code under contract, licensed game files | Read only by default | **No egress.** Output leaves through a `deliver` verb that shows name, size, hash, destination and class, and the person confirms. | A provider under contract terms, or local | An internal-only network with a no-tools model proxy. No terminal with internet, no browser, no web fetch, no `pip`, no `git push`. Encryption at rest per vault, key held by the person. Immutable backup (encrypted, private key off the host, append-only target on another host). Canary files plus host-side audit and byte counters, with a pause on trigger. No vault content in long-term memory. Short session retention. |
| **L4 Secrets and third-party personal data** | Keys, tokens, SSH, other people's personal data, operator infrastructure | **Never has them** | n/a | Never | Keys behind a credential proxy ([../KEY_SECURITY.md](../KEY_SECURITY.md)). SSH only through forced commands. Third parties' personal data never enters a workspace. Remove today's exposures: private SSH keys mounted in a stack, keys in the environment, the messaging token. |

### Honest limits

- **The model provider receives everything the model reads.** An egress allow list does not protect against that. So each level sets the **highest provider class** allowed, and the router must **degrade to refusal**, not to another provider, when a project is L2 or L3.
- **L2 is deterrence and a record, not a boundary.** Only L3 is a boundary, and even L3 does not cover the model provider unless the model is local or bound by contract.
- Integrity and confidentiality need different tools. Against deletion: backups, read-only mounts for reference assets, and a separate output directory. Against leaks: egress, keys outside the agent, isolated reads, provider class. A backup on the same disk, unencrypted, that skips large files fixes neither.
- Do not rely on what the agent's tool environment passes to child processes. The framework strips variables by name, and the list may miss some of ours. Root can read the container's process environment and config files anyway. Confirm with a canary on a guest stack before claiming either way.
- Other agent containers that share a person's workspace read-write (even stopped ones) break any L2 or L3 level. Retire them or unmount them before implementing levels.

## Phased plan

Order matters. The deny list is a hint to the agent, not a control. The real controls are the network closures in the first phase and the egress work in the later ones.

| Phase | What | Effort | Done when |
|---|---|---|---|
| **1: base** | Venv tooling in the image and a tested venv command, tried on a guest stack. New agent instructions using the `pkg` flow. Deny list for apt, apt-get, dpkg, sudo, `--break-system-packages`, `curl \| sh`, add-apt-repository, with a selftest. `allow_lazy_installs=false`. `NET_RAW` dropped on business stacks. Framework code root-owned or read-only. Remove dead config keys and fix misleading comments. | S | The startup selftest fails if a deny stops applying. On the guest, `uv venv` works and `apt install` is refused with the right message. |
| **1: network and watcher** | Watcher stage 0 (a `docker diff` timer plus bytes per stack, alerting the ops bot). Firewall rules cutting SMTP, outbound SSH and external DNS. A person with host root runs them, tested on the guest first. | S | A test install on the guest appears in the report as a count. An SMTP attempt from the guest fails. |
| **1: venvs and backups** | Rebuild or delete venvs built for an older Python. Start-time `pyvenv.cfg` check. Exclude venvs, large third-party binaries and browser libraries from backups. | S | No unflagged stale venvs remain. The person is warned if one exists. |
| **2: gateway** | `gateway pkg` with the catalog, hashes, a log and a request queue to the ops bot. Nightly job for missing tools. Outbound proxy in **report** mode. Strict media delivery from an outbox directory. Take the messaging token out of the agent's view. | M | A request outside the catalog reaches the operator and the person gets a clear answer. The weekly report lists the real hosts. |
| **2: narrower networks** | A power user's stack gets its own subnet with explicit pinholes instead of a blanket allow. SSH keys restricted on the target side (`from=` and a forced command). | M | The stack no longer has the blanket allow rule, and the connections it needs still work. |
| **3: enforce** | Outbound proxy in **enforce** mode with an allow list. Read-only root and custom seccomp, tried on the guest. Falco in alert mode, measured for a week, then canary pause. | M | Falco stays under the agreed CPU and RAM ceiling after 7 days. Zero false pauses in a week of enforce. |
| **3: L2** | Project mode: an open/close command, the manifest, a backup lane, and the router fixing the provider class from the project's level. | M | A test project opens and closes, and the provider class changes with it. |
| **4: L3 and beyond** | Vault: internal network with a model proxy, per-vault encryption, `deliver`, immutable off-host backup. Non-root and a VM per client stay separate projects. | L | A canary read in the vault pauses the stack and alerts. The vault has no network exit except the model. |

Measure before relying on them: Falco's cost on the real host, and whether the live firewall rules match the script on disk (needs root).

## Decisions for the operator

| # | Decision | Recommendation |
|---|---|---|
| 1 | Egress closed by default with an allow list for personal bots, even if it blocks ad-hoc downloads? | **Yes**, after a week in report mode. What is needed comes through the gateway. Open internet leaves data leaks unsolved. |
| 2 | Does the power-user bot keep `apt` and its allow list of code execution, or move to the gateway like the rest? | **Move to the gateway**, with a phone approval for anything outside the catalog. It holds the most keys and SSH access. Remove code execution from its allow list, or record it as an accepted exception. |
| 3 | Who picks a project's level, and what is the default? | The **person**, when creating the project. Default **L1**. Ask explicitly when IP, a licence or an NDA comes up. |
| 4 | Accept an optional vault mode with a local or class A model, where the operator **cannot** read it (the person holds the key and risks losing it)? | **Yes**, as an optional mode. Document the lost-key risk. Decide what counts as class A and whether an owned or rented GPU is the default. |
| 5 | Falco with automatic pause, or alerts only for a while? | **Alerts for a week**, then pause only on canaries and signal combinations. |
