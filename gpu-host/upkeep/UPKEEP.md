# upkeep: updating a host with a procedure, a rollback and a log

`upkeep.py` is the module that updates the machines the way a careful sysadmin would: the same steps every time, written as commands
the owner can copy, with a snapshot taken first so there is always a way back, a check after each risky step and an audit log of
what was done. It is stdlib Python, one CLI, and it never runs a command that needs root (the one command it runs that changes anything is the restart of the gate's *user* unit, see "GPU card management").

**Status: built and tested, not installed anywhere.** The bot skill that drives it (`aibridge/SKILL_host_upkeep.md`) is not in any image. It goes only to
the ops/technician stack, never into the shared image or the person-facing sysadmin pack; the wiring step is the `docker cp` line in the comment at the top
of the skill (same pattern as `aibridge/ops/install_claude_gate.sh`).

It covers the NVIDIA card of the GPU host as a whole: the driver (the case that has to be right: the driver carries the security fixes, and a
wrong update silently loses the `gpu-unlock` speed-up), the unlock, a kernel update, the power caps and VRAM needs the bench measures, and new
gpu-host code for the gate (see "GPU card management"). Other procedures plug in the same way (see "Adding a procedure").

## Principles

- **Security updates are applied fast.** `driver_watch.py` classifies an update as `security` from NVIDIA's bulletins; that one is done
  as soon as the card is free, not measured first.
- **Other updates only if they unlock performance, and only after measuring.** A `performance` or `unknown` class means: update, run
  the selfcheck, bench the real jobs, keep it only if nothing is slower or costlier, otherwise roll back.
- **The owner (a human) runs anything that needs root.** The bot prepares, explains, checks what the owner pastes, verifies and keeps
  the log. The tool prints root steps; `Sys.cmd` refuses to start anything but a short list of read-only programs
  (`dpkg-query`, `apt-cache pkgnames|madison|policy`, `apt-mark showmanual`, `dkms status`, `uname -r`, `nvidia-smi`, and read-only `git rev-parse` and
  `git archive` of `gpu-host/` in this checkout). `--apply` exists only for steps that need no root. The one program that changes anything is
  `systemctl --user restart bridgeai-gate.service` (`Sys.act`, exactly that argument list; the gate is a user unit).
- **Nothing is ever lost.** The gate's busy switch is turned on before the work and off after a good verify: the gate refuses new wakes,
  running services finish by themselves, jobs wait or go to the next host. Nothing is cut.
- **Tell people before a GPU window.** The ops bot says when the card will be unavailable; the stacks use the next host meanwhile.

## Why the pin and the driver are two apt transactions

The driver is held by a pin package (`nvidia-driver-pinning-<version>`, which writes `/etc/apt/preferences.d/nvidia-driver-pin`). apt reads
that pin at the START of a transaction. In a test run on Debian 13, `apt install nvidia-driver-pinning-NEW nvidia-open ...` in one command changed the
pin and printed "nvidia-open is already the newest version (OLD)" for every driver package: the old pin was still
in force while apt computed the plan. The working procedure is two transactions:

1. install the new pin ALONE (plus `nvidia-container-toolkit` if upgradable);
2. then install the driver packages (`--no-remove`: apt itself refuses a removal): the simulation upgraded 58 packages to the new version, removed nothing, and kept
   `gpu-unlock-dkms` and `gpu-unlock-firmware`.

Rolling back has the same shape: the old pin alone first, then the driver packages at explicit `=versions`.
`fixtures/` holds both outputs, rebuilt (`sim_one_transaction.txt`, `sim_driver_after_pin.txt`), and the selftest uses them.

## The procedure (driver)

`python3 gpu-host/upkeep/upkeep.py plan driver --to VERSION` prints, from the first line, `run from the bridgeai checkout: cd PATH` (the commands are written relative
to the checkout: the owner is usually in a home directory), then the preflight and these steps, with this host's package names. VERSION must be digits and dots
(`595.112.07`); anything else is refused by the argument parser, because it ends up inside `sudo apt install` lines. Steps are tagged `[owner, root]`,
`[owner, no root]` (the simulations) and `[bot, no root]`. With a `NOT OK` anywhere in the preflight **no steps are printed** (the one exception is a stale package
list: the repo line alone is NOT OK, and the plan says `sudo apt update`, then plan again).

| # | who | step | what to look for |
|---|---|---|---|
| 1 | bot | `busy on --apply` | `busy: on` |
| 2 | bot | `idle` (repeat) | `idle: yes`; else it names what still runs (a service, a lease, a bench, a person on the card) |
| 3 | bot | `snapshot --apply` | `snapshot saved: <id>`: the rollback source |
| 4 | owner | `sudo apt update` | no errors; NVIDIA repo fetched |
| 5 | owner, no root | `apt install -s <pin> [toolkit] \| upkeep.py check-sim - --pin --to NEW` | `check-sim: ok` (only the pin swap and the toolkit) |
| 6 | owner | `sudo apt install nvidia-driver-pinning-NEW [nvidia-container-toolkit]` | old pin removed, new pin installed, no driver package in it |
| 7 | owner, no root | `apt install -s --no-remove <driver packages> \| upkeep.py check-sim - --to NEW`, or `> FILE 2>&1` and the bot runs `check-sim FILE --to NEW` | `check-sim: ok` |
| 8 | owner | `sudo apt install --no-remove <driver packages>` | no errors; DKMS builds nvidia and gpu-unlock for every kernel with headers |
| 9 | bot | `verify --to NEW --installed`, `dkms status` | ok; nvidia/NEW and gpu-unlock installed for every kernel with headers |
| 10 | owner | `sudo reboot` in a quiet window | host back, gate answers |
| 11 | bot | `verify --to NEW --apply` (`timeout=300`; the selfcheck stops itself at 240 s) | `RESULT: ok` (gate opens again) or `RESULT: degraded` (rollback printed, gate stays closed) |
| 12 | bot | `bench_gate.py --recheck` (only for a non-security update) | no slowdown, no extra Wh |

The driver packages are the manually installed ones of the NVIDIA driver family that dpkg has on the host (as `driver_watch.py` derives
them), not the pin, `gpu-unlock*` or the container toolkit.

### Preflight

- the target is newer than the installed driver, and offered by the configured repo (`apt-cache pkgnames nvidia-driver-pinning-`, `madison`);
  if the lists are stale (the repo line is the only NOT OK), the owner runs `sudo apt update` and the plan is run again; any other NOT OK stops;
- every package name that goes into a command line is dpkg-safe (checked, not trusted);
- exactly one pin package installed; driver packages found; `gpu-unlock-dkms` present or not;
- DKMS already built for every kernel with headers (a gap now is reported), and installed kernels without headers (a note);
- `/boot` has room for the initramfs rebuild of every kernel (biggest initrd x 1.5, at least 200 MB; `UPKEEP_BOOT_MIN_MB` overrides);
- the gate answers `GET /state` with `GATE_TOKEN` from host.env (never printed) and nothing runs on the card (`wait` means steps 1-2 handle it);
- the class and `unlock_mismatch` from `driver_watch.json`, when it has one for this target.

### check-sim

`check-sim [FILE|-] [--to VERSION]` reads a saved `apt install -s` output (apt 2 and apt 3 formats; a `> ` quoting or an indentation of the whole paste is ignored).
It says **not ok** when:

- **pin not swapped**: a driver package is "already the newest version" at the old driver (with the new pin in the same output it names
  the one-transaction cause);
- a driver package goes to a version other than the target, or is kept back;
- **anything is removed except the old pin**: a driver update removes nothing else. Protected packages (`gpu-unlock*`, the running kernel's image and headers,
  `linux-image-amd64`, `dkms`, the container toolkit, docker/containerd, sshd, systemd, sudo; `UPKEEP_PROTECT` adds regular expressions) and driver packages have
  their own reason; any other removal (a desktop package, a CUDA toolkit, the pending kernel) says "a driver update removes nothing but the old pin".
  `UPKEEP_ALLOW_REMOVE` (regular expressions, comma separated, whole package name) lists an exception, and the operator sets it. The printed install line
  has `--no-remove` too, so apt itself refuses;
- **coverage**: the plan installs a list of driver packages (the host's manually installed ones); every one must appear in the simulation (installed or already at
  the target). A simulation of `nvidia-open` alone is not ok;
- apt printed an `E:` line or "unmet dependencies";
- it installs only the pin (that is the pin step, not the driver step) or nothing at all.

Reasons and notes are capped (the count of the rest is printed). The old pin being replaced is expected and is a note. A package with its own version scheme (a CUDA
toolkit) is not judged against the driver. `ok` also notes that `firmware-nvidia-gsp` is upgraded: `gpu-unlock-firmware` was only checked with the old driver, so
the selfcheck after the reboot decides.

`check-sim --pin --to V` judges TRANSACTION 1: it must install the pin of V, may remove an older pin, may upgrade container packages, and nothing else.
`check-sim --rollback-from SNAPSHOT --to OLD` judges a rollback: a driver package that is not in the snapshot (it came with the update) may be removed, and coverage
is the list of packages that differ from the snapshot. A file that cannot be read ends with exit 2 and a one-line message, not with the exit code of "not ok".

**How the bot gets the verdict.** The owner runs the printed pipe (the simulation needs no root) and reads the bot the first line, `check-sim: ok (target V)` or
`check-sim: not ok (target V)`; or the owner writes the simulation to a file and the bot runs `check-sim FILE --to V`. hostcare's `run(command, reason)` takes only a
command string, so reading a paste would mean putting a person's text inside a shell command: that is never done. The bot reads a file, or the one-line verdict.

Other installs in a driver simulation are judged too: a new kernel image or headers in it is a **reason** (DKMS rebuild and `/boot` risk: do `plan kernel` first, separately); any other non-driver
install is listed as a note.

### verify

`verify --to V --installed` (before the reboot): the one installed pin is V's, every driver package is at V (a family package with its own version scheme is named
and not judged), `dkms status` shows nvidia/V
and gpu-unlock `installed` for every kernel that has headers. A FAIL means do not reboot.

`verify --to V --apply` (after the reboot): the above, plus `nvidia-smi` reports V, the running kernel has its DKMS build, the gate answers,
and then `gpu_selfcheck.py run --force` (ok / degraded). The selfcheck measures inside the gate's bench mode, which refuses while the busy
switch is on, so verify lifts the switch for the measurement (the gate is open to new wakes for that whole window: inherent, a few minutes at most) and puts it
back unless the verdict is ok. Three layers keep the gate from staying open on an unverified driver:

1. a `finally` puts the switch back after an error, Ctrl-C or SIGTERM (the tool turns SIGTERM into an exit during the selfcheck);
2. the selfcheck has a **hard stop of 240 s** (`UPKEEP_SELFCHECK_TIMEOUT_S` can only lower it, never past 280 s), below hostcare's 300 s `run` maximum, so hostcare's kill does not come
   first in the normal case; a selfcheck that does not finish is stopped with its whole process group and the result is `incomplete` (gate closed, run it again when the card is free);
3. a **SIGKILL** (which no `finally` survives) is covered by the marker `verify-in-progress.json` in the state directory: it is written BEFORE the switch is lifted (pid, step, the
   selfcheck's own pid) and removed only after the switch is back. **Every later upkeep call** (idle, busy status, plan, verify, undo, log, ...) first looks for it; when the process that
   wrote it is gone (or the marker is older than any selfcheck can last, or unreadable) the call prints `RECOVERED` on stderr, closes the gate again (busy on), stops the orphaned
   selfcheck (only a process whose command line is the recorded script), logs `verify-recovered` and removes the marker. A marker whose writer is still running is left alone.

`unlock --run --apply` uses the same guard (step `unlock`). `verify`
checks also that the newest installed kernel (and any kernel in `/boot`) has headers: grub boots the newest one, and without headers there is no DKMS build and the
host comes up without the driver (an older kernel without headers is a note):

- `ok`: busy stays off, one log line;
- `degraded` (the unlock did not survive) or a failed check, before or after the selfcheck (`--apply`): busy ON, the rollback commands printed, a log line;
- no verdict (card in use, selfcheck error): busy ON, exit 2, run it again.

Without `--apply`, verify checks everything read-only and stops with `RESULT: incomplete`.

### rollback

`rollback [SNAPSHOT]` (default: the newest snapshot whose driver is not the one installed now; the others are listed) prints, from the snapshot: the old pin alone
(with its own `check-sim --pin`), then `apt install --allow-downgrades pkg=version ...` for every driver package, container package and `gpu-unlock*` whose version differs,
`check-sim --rollback-from SNAPSHOT --to OLD`, `dkms status`, the reboot, and `verify --to OLD --apply`. The preflight, and **no steps when any item is NOT OK**:

- the snapshot is usable: a driver version, a `packages` table (a string or a missing table is refused), and every name and version dpkg-safe (they end up in
  `sudo apt install` lines); a snapshot file is data, not trusted;
- the old pin package is still offered (else transaction 1 would fail after the gate is closed; a stale list: `sudo apt update`, run again);
- every package is still offered at its exact old version (`apt-cache madison`, compared as whole versions, not as text);
- `/boot` has room, the gate answers.

`--no-remove` is on the printed downgrade line unless packages that came with the update must go, in which case `check-sim --rollback-from` judges instead of apt.
The container toolkit is in the line (it is part of the snapshot): the owner may drop it if only the driver is the problem, which keeps the toolkit's own fixes.
It refuses when the host already equals the snapshot. A rollback of a security update leaves the host exposed: the owner decides, and the reason goes in the log.

## Snapshot, state and audit log

State is in `$UPKEEP_STATE_DIR` (default `~/.local/state/bridgeai-upkeep/`), directories 700 and files 600, re-applied on every use:

- `snapshots/<UTC time>.json`: installed versions of the whole driver family (the same pattern the plan uses: `nvidia*`, `libnvidia*`, `firmware-nvidia*`,
  `xserver-xorg-video-nvidia`, `cuda-drivers`, `libcuda1`, `libnvcuvid1`, `libegl/libgles/libglx-nvidia*`), `nvidia-container*`, `gpu-unlock*` and the pin, the driver package set, running and installed kernels with their image and header packages, `dkms status` rows
  and `/boot` free space. Take one before every update (`snapshot --apply`); `snapshot --list` lists them. The snapshot is **refused** unless the host is in a clean state
  (driver known; the pin, the running driver and every driver package at the same version): a half-updated state would shadow the good snapshot. `--force` saves it anyway
  and the log says `forced`.
- The directory is per account: set `UPKEEP_STATE_DIR` to the same path for the owner's account and the bot's, or a rollback run by the owner finds no snapshot.
- `audit.jsonl`: append-only by `O_APPEND` and file mode 600 (a record, not a tamper-proof one: anyone with the account can edit it), one JSON line per action: `at`, `ts`, `step`, `result`, `versions`, `note`. `log` shows it (`-n N`, `--json`).
  The tool writes a line for busy on/off, snapshot, check-sim, plan and rollback-plan (with `--apply`) and verify; the bot records the owner's
  root steps with `log --add STEP --result done --note TEXT --apply` ("owner-apt-update", "owner-apt-pin", "owner-apt-driver", "owner-host-restart").
  The step names and notes must not contain a word hostcare's NEVER list refuses (`reboot`, `shutdown`, `poweroff`, `halt`, `passwd`...): hostcare matches the whole command, so
  `owner-reboot` is refused and never recorded. The selftest runs every command the skill and the plans print through hostcare's real NEVER regexes.

## GPU card management

The same module covers the card as a whole. Four things change a GPU host's behaviour, and each one has a before/after record and an exact way back:

| change | what moves | procedure | way back |
|---|---|---|---|
| NVIDIA driver | packages, pin, DKMS | `plan driver` (above) | `rollback` |
| kernel | image, headers, DKMS builds | `plan kernel` (print-only) + `unlock --kernel` | boot the old kernel; `rollback` for packages |
| power caps and VRAM needs | `power_profiles.conf` section of the card, `gate/gate.py` SERVICES | `plan profile` | `undo ID` |
| gate code | the deployed `gpu-host/` tree, `~/bin/mcp_dispatch.sh` | `plan deploy` | `undo ID` |

They are tied together by one rule: **a driver, an unlock or a kernel change makes the numbers of the last bench stale.** After any of them the unlock is checked
(`unlock`), the real jobs are benched again (`bench_gate.py --recheck`), and `plan profile` turns the new measurement into caps and VRAM needs, shown as a diff first.
`unlock` says when a re-bench is due: the bot records each bench with `log --add bench --result done --ref RUN --apply`, which stores the driver, kernel and
`gpu-unlock` versions it was measured on, and `unlock` compares them with now.

Every procedure below prints by default. `--apply` is for what needs no root: the files of the gpu-host copy the gate runs from, and the restart of the gate's user
unit. Nothing here needs `sudo`.

**Where the files are.** `--dest DIR` is the gpu-host copy the gate runs from. On a standard install (`gate/install_gate.sh` writes a unit that runs `gate.py` from the checkout) **the checkout and
the deployed copy are the SAME files**: `plan profile` edits git-tracked files of the checkout, and `plan deploy --from-ref` over it rewrites the working tree. So there is **never a default destination inside the source checkout**: with no `--dest` (the default is `$UPKEEP_GPU_DIR`, else the tree this tool sits in) a destination inside the checkout is a NOT OK that tells you
to spell `--dest DIR` out, so the owner reads the target in the command. With `--dest` inside the checkout the plan notes it, and (when DIR is the checkout's own `gpu-host/`) runs a
read-only `git status` on it: a **dirty git tree** is a warning that lists how many files have uncommitted changes and which of them this deploy would REVERT to the source's copy.
The tool also reads what the gate really reads (the unit file `~/.config/systemd/user/bridgeai-gate.service` is only READ: its `ExecStart` gate.py, `Environment` and `EnvironmentFile`, the
gate's own `GATE_ENV_FILE` or `host.env`, then `GATE_POWER_PROFILES`, exactly as `gate.py` computes them). `plan profile` refuses (NOT OK) to edit a `power_profiles.conf` or a tree the
gate does not read; `plan deploy` warns. The restart is `systemctl --user restart` and only works as the gate's own user: with no unit file for the account the plan says so.
**Every** `UPKEEP_*` environment variable in effect (`UPKEEP_ALLOW_REMOVE`, `UPKEEP_PROTECT`, `UPKEEP_GPU_DIR`, `UPKEEP_STATE_DIR`, `UPKEEP_BOOT_DIR`, `UPKEEP_BOOT_MIN_MB`, `UPKEEP_CHECKOUT`,
`UPKEEP_SELFCHECK`, `UPKEEP_TEST`, and any other name) is printed on stderr at every call as `upkeep: OVERRIDE: ...`, shown as `note override` in a plan, and written once to the audit log
(an `override` line, again only when the set changes; a deploy or profile change also carries it in its before line), so a command that carries one is visible to the owner who approves it.
They cannot all be blocked here, because the operator uses them too, with two exceptions that are **test-only**: `UPKEEP_SELFCHECK` (another script for `verify`) and `UPKEEP_CHECKOUT` (another git
checkout) are honoured only when `UPKEEP_TEST` names the selftest's marker file (`upkeep-selftest.marker`, a file only `upkeep_selftest.py` creates: owned by this user, mode 600, under the temp
directory, written in the last six hours, holding the magic line). `UPKEEP_TEST=1` is not enough; outside the selftest both are printed as `IGNORED`. Whoever can create that file could already run
any script as this user. git is always started with `-c core.fsmonitor=false` (a repository's `core.fsmonitor` is a program `git status` would run); a filter driver that the owner's own
repository config and `.gitattributes` define is the owner's and is not blocked.

**One change at a time, and a bounded backup store.** Every `--apply` of profile, deploy and undo holds an exclusive lock (`apply.lock` in the state directory): a second one refuses at
once. After a change only the newest `UPKEEP_KEEP_BACKUPS` backups (default 20, at least 3) are kept; the removal is printed and logged (`backups-pruned`). **Disk use**: a deploy backs up
the whole deployed tree (the tool refuses a tree over 200 MB and checks the free space first), so 20 backups are up to 4 GB in the state directory; lower `UPKEEP_KEEP_BACKUPS` (not below 3) on a small disk.
**`--dest` that is itself a symlink** (for example `~/gpu-host` pointing at the checkout) is accepted with a note: the files are read, written and backed up in the real directory and undo puts them
back there; only symlinks INSIDE the tree are refused. A `--dest` inside another git work tree gets a note that the dirty-tree check is made only for the source checkout. A relative
`GATE_POWER_PROFILES` is NOT OK for a profile change (the gate resolves it against its own working directory, which this tool cannot know). **Special files** (a fifo, a device, a directory where a file
should be) are never opened: deploy, profile and undo refuse them (`not a regular file`), and a state-directory file that is one is read as empty or unreadable instead of hanging the tool. **Exit code**: 0 only for
`RESULT: ok`; `degraded` (a service that ran is not listed again) and `failed` are 1.

### The gate restart rules (profile, deploy, undo)

The gate reads `power_profiles.conf` and `gate.py` only when it starts, so a change takes effect with a restart. A restart drops the gate's leases and the gate
**adopts** the services that already run (they then follow the idle rule), so it is safe with services running only because of that adoption, and that is why it needs a
flag:

- no service running or leased (`GET /state`): the gate is restarted by the tool;
- a service runs: **refused before any file is touched**, unless `--restart-while-running` (relies on the adoption) or `--no-restart` (files only; the running gate keeps the
  old values until its next restart);
- a bench or selfcheck runs: refused always (a restart would end the measurement);
- the gate answers `/healthz` but not `GET /state`: refused (cannot tell whether a service runs); the gate down: started, nothing to protect.

After the restart the tool checks `/healthz`, then `GET /state`, and that every service that ran before is listed as running again (otherwise `degraded`). A change that does
not touch what the gate loads at its start (a deploy that only changes `resolve_mcp/`) restarts nothing.

### Profile apply: `plan profile [RESULTS] [--run ID] [--dest DIR] [--ref TEXT]`

Input is `bench_gate.py`'s `results.jsonl` (default `$BENCH_GATE_HOME/results.jsonl`, else `~/bench_gate/`): the newest run's `recommend` rows, which are the printed
"Proposed (nothing is edited)" block in data form. The tool takes a **power cap** per service for the card's section of `power_profiles.conf` and a **VRAM need** per
service for the `SERVICES` table of `gate/gate.py`. It skips (with a note) a task the gate does not know, a cap outside the card's range (the gate's `min_w`..`max_w`), a VRAM
figure that is informative only (ComfyUI's dynamic VRAM: never a threshold), and `imggen`/`vidgen` numbers measured with gpu-unlock off.

Preflight (any `NOT OK` ends with no diff): the results are readable; the run has a session row naming the card; **the card's section exists** in the deployed
`power_profiles.conf` (the one the gate itself would pick: the longest section name that is part of the GPU's name; the tool never creates a section); the card the gate reports is
the one the numbers were measured on; the deployed `gate.py` reads (its `SERVICES` literal is parsed, never run); the edit changes nothing but the proposed values (the
edited table is parsed again and ports and ready budgets must be unchanged); **the gate reads these files** (see "Where the files are": a different `GATE_POWER_PROFILES` or tree is NOT OK);
neither file is a symlink or sits behind one; an existing line of the card's section for a service being changed is a plain `key = number` (`llm = fast` is a NOT OK at the dry run, not a failure after
the owner said yes). Numbers must be **finite whole numbers in range** (`NaN`, `Infinity`, fractions and strings, which `json.loads` accepts, are skipped with a note, also in the gate's own
card range); a VRAM need below 64 MB is skipped, and one that **falls by more than 25%** from the value in `gate.py` is a NOT OK (a lower need lets the gate over-commit the card) unless
`--allow-lower-need`, which the printed apply command then carries. A failed write restores both files; a gate that does not come back after the restart is rolled back at once, as in a deploy.

Then the **diff**, a one-line list of changes, the gate rule and a **confirm id** (a hash of the diff). `--apply --confirm ID` is the confirmation that the owner saw *that* diff:
a changed result or file changes the id. It then: backs up both files (`$UPKEEP_STATE_DIR/backups/ID/`, md5 per file, directories 700, files 600, manifest), logs the before line,
writes both files atomically, reads them back (the section parses the way the gate parses it, the table reads, the values are the proposed ones; otherwise it restores and says
so), restarts the gate by the rules, and logs the after line. The same proposal run again says "nothing to change".

### Gate deploy: `plan deploy --from-ref REF | --from-dir DIR [--dest DIR] [--mcp-dispatch PATH | --no-mcp-dispatch] [--ref TEXT]`

A new `gpu-host/` tree over the deployed copy, from a **git ref of this checkout** (read-only `git archive` of `gpu-host/` at that commit; the commit id is what the log records) or from
a **directory**. Never copied, backed up or restored, whatever the source holds: `host.env`, `state/`, `*.log`, `__pycache__/`, `out/`, `models/`, `.git/` (the host's own data and
secrets). Symlinks and special files are not deployed. Files only in the deployed tree are kept, never removed.

**This tool never replaces or deletes a symlink.** Preflight: a file the deploy would write that is a symlink, sits behind a symlinked directory, or whose new path is already a special file is a
NOT OK (an undo would otherwise delete the link). Writes go through a temp file made with `O_EXCL` and `O_NOFOLLOW`, then a rename; the target and every directory below the destination are
checked again at write time. **A failure in the middle of the copy** (a full disk, a read-only file) restores every file from the backup, logs `failed` and does not touch the gate. Warnings
(not blocks): a dirty git tree and the files it would revert, files a still-effective **profile change** wrote (found in the manifests, by change id: run `plan profile` again afterwards), a gate
that does not run from or read this tree.

Preflight: the source holds `gate/gate.py`; the destination is a deployed `gpu-host` tree (it has `gate/gate.py`; nothing is ever written into another directory); source and
destination differ; every changed Python file compiles (`ast`, nothing runs); room for the backup; the gate rule. Then the counts, `gate.py`'s md5 before and after, the list of
files (capped) and a confirm id. `--apply --confirm ID`: **full backup** of the deployed tree (every non-excluded file) under `backups/ID/tree/`, the changed and added files
copied atomically (mode kept, execute bits taken from the source), every md5 read back against the source, the gate restarted by the rules, `/healthz` and `/state` checked, before and
after lines logged (md5 of `gate.py`, a digest of the tree, the source). **A gate that does not answer after the restart is rolled back at once** (files restored, the restart
tried again, logged `rolled-back`): a GPU host with no gate is out of rotation. Services that were running are listed as running again, else the result is `degraded`.

`~/bin/mcp_dispatch.sh` is a separate copy of the tree's `mcp_dispatch.sh` (the forced command of the MCP-only SSH key): when it exists (or `--mcp-dispatch PATH` names it) it is
replaced by a plain copy with its own backup, mode kept; `--no-mcp-dispatch` leaves it alone. The path must be named `mcp_dispatch.sh`, be a regular file (not a symlink: many installs link it, then give
the real file with `--mcp-dispatch` or skip it) or absent, in an existing directory; anything else is a NOT OK before a byte is written. `resolve_mcp/` travels with the tree.

### Undo: `undo [CHANGE_ID] [--apply] [--force] [--no-restart] [--restart-while-running]`

Without an id it lists the changes that have a backup. With one it prints what it restores (current md5 -> the backup's) and the gate rule; `--apply` restores every file exactly
(md5 checked against the backup, a file the change added is removed, the old dispatcher is back), restarts the gate by the rules and logs. It **refuses files that were changed after
the change** (a later change or a hand edit) unless `--force`, refuses a manifest whose paths do not belong to its recorded destination, and a second undo says "already undone". A file of the change that is now a **symlink** (or sits behind one) stops the undo (`NOT UNDONE`, nothing deleted or replaced); with `--force` the other files
are restored and the symlinked ones are skipped and reported (`RESULT: failed`). A missing or altered backup stops it too, and `--force` does not help there (the message says so). A restore that
stops midway (disk, permissions) says so and names the command to run again. A change that failed and could not be restored says **the restore FAILED / HALF-DEPLOYED** (headline and
audit result `failed-restore-failed` or `rollback-failed`, with the `undo ID --apply --force` line), never "every file was put back"; the headline follows the real state of the files. An undo that
left files different from the backup does not mark the change as undone.

### Unlock check: `unlock [--run] [--kernel RELEASE]`

Wraps `gpu_selfcheck`'s result and the `gpu-unlock` checks of `driver_watch` into one verdict, **ok / degraded / unknown** (exit 0 / 1 / 2; the first line is the verdict):

- **degraded**: the selfcheck says degraded (words: `fp32acc_slow`, ...), a `gpu-unlock` or nvidia DKMS build is missing for a kernel with headers, or `gpu-unlock-firmware` is missing;
- **unknown**: `gpu-unlock-dkms` is not installed, there is no selfcheck result yet, it could not judge (`no_reference`), or the last result is for another driver, kernel or
  `gpu-unlock` version (stale: `unlock --run --apply` measures now);
- **ok**: everything above agrees and the result is fresh.

Notes, never a verdict: a newer stable upstream `gpu-unlock` (a performance change: measure first, then update like the driver), a pre-release only (not recommended), the apt candidate, an old
`driver_watch` answer, and whether a **re-bench is due**. `--run --apply` runs the selfcheck first with the same busy handling as `verify` (lifted for the measurement only when it was on,
put back unless the verdict is ok, also after a crash). `--kernel RELEASE` adds the new kernel: image, headers and both DKMS builds must exist, or it says **DO NOT RESTART** into it. Like `verify`, `unlock` FAILs when the newest installed kernel (or a
kernel in `/boot`) has no headers (grub boots it, no DKMS build): it never says ok for a host that would come up without the driver. `--run --apply` also writes the verify marker.

### Kernel update: `plan kernel [--to RELEASE]` (print-only)

The release comes from `--to` or from the one pending kernel `driver_watch` sees. Steps: busy on, idle, snapshot, `apt update`, simulate `linux-image-amd64 linux-headers-amd64` and read it with
`check-sim --kernel` (every new image comes with its headers, nothing is removed, and no driver or `gpu-unlock` package rides along: the driver has its own procedure; other installs are listed as a
note; the printed `apt install` lines carry `--no-remove`), install, then **`unlock --kernel RELEASE` before the restart** (nvidia and gpu-unlock built for the new
kernel, else no restart: a kernel without the module comes up without the driver), the owner restarts, `unlock --run --apply` decides and opens the gate only on ok, then the re-bench and
`plan profile`. Rollback: boot the previous kernel from the boot menu (it stays installed); no package change.

### The change log: before and after for every change

Every change writes two lines to `audit.jsonl`: a `before` line (written before anything is touched: `what`, the md5s or versions before, the measurement it rests on, the command that undoes
it) and an `after` line (the result, the md5s or versions after, the rollback command again). `verify` ok writes the driver before and after and the `rollback SNAPSHOT` command; `snapshot`
names its id. `log --history` prints the changes only, with `before:`, `after:`, `ref:` and `rollback:` lines, so a host's history can be read in one screen; `log --json` is the raw record.
`--ref TEXT` on the procedures and on `log --add` carries the measurement reference (a bench run id).

**The events stay on the host.** The log, the snapshots, the backups and their manifests live in `$UPKEEP_STATE_DIR` (mode 700 / 600). They are never committed: this repository holds the
tool, its tests and fake data, not any host's history, host names, addresses or uptime.

## Who runs what

The owner needs nothing but a shell on the host. The ops bot reaches the host through hostcare (`aibridge/ops/hostcare/HOSTCARE.md`): the
commands of the bot column above are `run(command, reason)` calls, level 2, so the operator approves each; hostcare's NEVER list (reboot, power,
secrets) is why the flag is `--installed` and why a reboot is always the owner's. `run` times out at 120 s by default and 300 s at most: pass `timeout=300` for `verify` and
`snapshot`; exit 124 means "run it again". The tool's own selfcheck stop (240 s) comes first; if hostcare kills the tool anyway (SIGKILL, no `finally`), the busy switch is NOT put back by that
run: the verify marker makes the **next** upkeep call close the gate again (see "verify"), so the claim is "closed again by the next call", not "never open for a moment". hostcare's NEVER list has no apt, dpkg or dkms entries, so "the bot never runs root" rests on the skill, the operator's approval
and the tool's own allowlist, not on hostcare's code; the operator may add them to `never` in hostcare.json: `apt(-get)?\s+(install|remove|purge|upgrade|dist-upgrade|autoremove)`,
`dpkg\s+-i`, `dkms\s+(install|remove|build)`. The only program besides the read-only ones that `verify --apply` starts is `gpu_selfcheck.py`, which starts its own throwaway
docker probe through the gate's bench (not apt, dpkg or dkms; the environment cannot point it elsewhere unless `UPKEEP_TEST` names the selftest's marker file, which only the selftest creates). Promoting `upkeep.py` read-only commands to named level-1 tools
is the operator's call. The skill that tells the bot how is `aibridge/SKILL_host_upkeep.md`.

## Adding a procedure

A procedure is one function and one entry in `MODULES` in `upkeep.py` (the `plan` subcommand is built from it). A module that does its own work with `--apply` (profile, deploy: backup,
write, restart, before/after log) is also in `ACTING`, so the dispatcher does not add a second log line; a check without steps (`unlock`) is one function and one entry in `CHECKS`:

1. **Facts first.** Reuse `facts(S)` (packages, kernels, headers, dkms, running kernel, driver) and add what the new procedure needs through
   `Sys.cmd` only. A new read-only program is one line in `Sys.ALLOWED`; a root program never goes there.
2. **`plan_<name>(S, env, args) -> (lines, ok)`**: a preflight list of `(status, name, detail)` (`ok`, `NOT OK`, `wait`, `note`) and the steps as
   `(who, what, command(s), what to look for)` for `fmt_steps`. The first steps are always: busy on, idle, snapshot. Root steps say `owner`.
3. **A check of the simulation** if the procedure has an apt simulation: a pure function over the pasted text that returns reasons, like
   `check_sim`, with a selftest on a representative output and on the output that must be refused.
4. **A verify**: the state it must reach, in the same `(status, name, detail)` shape, and what decides between ok, degraded and incomplete.
5. **A rollback** from the snapshot: extend `snapshot_of` if the procedure needs more state than it records.
6. **Selftest** in `upkeep_selftest.py` with the PATH fakes: the plan, a refused simulation, verify ok and failed, and that the root-command
   traps stay untouched.

Sketches (not built):

- **Kernel update**: built as `plan kernel` (print-only), see above.
- **Container toolkit**: simulate `nvidia-container-toolkit*` alone; verify with a throwaway `docker run --gpus all` that sees the card; rollback to the
  snapshot's `=versions`. No reboot, but the docker daemon restart is the owner's and needs an idle gate.
- **gpu-unlock versions** (not built; `unlock` already reports them): the same two-transaction care is not needed (its own version), but it is a performance change: measure first
  (selfcheck, bench), DKMS rebuild per kernel, verify, rollback to the snapshot's `gpu-unlock-*=version`.

## Tests

`python3 -I gpu-host/upkeep/upkeep_selftest.py` (also in `aibridge/ops/run_selftests.sh`; run it with `TMPDIR` set to a fresh directory): fake `dpkg-query`, `apt-cache`, `apt-mark`, `dkms`, `uname` and
`nvidia-smi` on PATH, a fake gate (a local HTTP server that checks the token), a fake selfcheck, and trap versions of `sudo`, `apt`, `apt-get`, `dpkg`,
`reboot`, `modprobe`, `update-initramfs` and `dkms install` that fail the test if they are ever started. `--show` prints the sample outputs. It also covers:
removals other than the old pin, coverage, quoting, `--pin`, `--rollback-from`, the whole-family snapshot, a half-updated snapshot, hostile `--to` and snapshot text, the
rollback preflight, the busy switch on a crash, kernels without headers, and every command the plans and the skill print against hostcare's NEVER list.
The card procedures have fakes of their own: a deployed `gpu-host` copy in a temp directory (the real `gate.py` and `power_profiles.conf` as the base, host data files that must never move),
a `results.jsonl` with several runs, a fake `systemctl` that accepts only the exact restart of the gate's user unit (it writes a line to a file and restarts nothing; any other form is a trap),
a fake gate with `/healthz` that can go down, and a throwaway git repository for `--from-ref`. They check: backup made with equal md5s and modes 700/600, the diff shown before anything is written,
the confirm id, the gate restart refused while a service runs unless the flag (and always while a bench runs), only the proposed files changed and every excluded file byte for byte intact,
`undo` restoring the md5 of every file (and refusing a later hand edit and a hostile manifest), the gate that does not come back rolled back, hostile ids/refs/releases refused by the parser, the
unlock verdicts, the kernel gate before the restart, the before/after log lines, and every printed command against hostcare's NEVER list. The review-round block covers: symlinked files, directories
and special files in the destination and in `--mcp-dispatch`, the temp-file writer (`O_EXCL`, `ELOOP`), undo with a symlink, the checkout-as-destination rule with a throwaway git repository (dirty
tree, files that would revert), profile values a deploy would revert, what the gate unit reads, the SIGKILL and SIGTERM of a verify and its recovery by the next call (the fake selfcheck kills its own
parent), the hard timeout, a write error in the middle of a copy, NaN/Infinity and odd lines, a falling VRAM need, other installs in a simulation, `unlock` and kernels without headers, non-object
log lines, degraded exit codes, a profile rolled back when the gate does not return, the lock, pruning and the printed overrides.
The fifth review round adds: a forged verify marker (an unrelated process, a wrong script text, not a group leader, another uid), a marker that cannot be removed, headlines and audit results of a
restore that fails (a full disk injected in-process), fifos everywhere a file is read, every override and the selftest marker, `git status` with `core.fsmonitor` set, destinations in other work trees
and behind a symlink, a symlinked audit log, CRLF files, leftover temp files and the VRAM need range.
