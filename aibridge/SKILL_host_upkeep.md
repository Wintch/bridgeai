---
name: host-upkeep
description: "Update and tune the operator's GPU host with a procedure, a rollback and a log (for the ops/technician bot and hostcare): the NVIDIA driver, the kernel, the unlock check, power caps and VRAM needs from the bench, new gate code. Security updates now, other updates only if they unlock measured performance, the owner runs every root step. Tool: `upkeep.py` (plan, check-sim, verify, rollback, undo, unlock, log). Triggers: actualizá el driver, hay una actualización de seguridad, update the GPU host, rollback del driver, aplicá el perfil del bench, desplegá el gate, обнови драйвер, откат обновления."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [sysadmin, updates, nvidia, driver, rollback, gpu, security, procedure, audit]
---

<!-- Status: NOT installed. This skill goes ONLY to the ops/technician stack (the one that holds the hostcare tools), never into the shared
     image or the person-facing sysadmin pack. Wiring step, run by the operator, same pattern as aibridge/ops/install_claude_gate.sh:
       docker cp aibridge/SKILL_host_upkeep.md <ops-container>:/root/.hermes/skills/devops/host-upkeep/SKILL.md
     If it ever goes into the shared image it also needs a skill_packs.json entry, a gen_capabilities.py row and a regenerated capabilities_index.md. -->

# Host upkeep: update a machine with a way back

You prepare, explain, check and keep the record. **The owner (a human) runs anything that needs root. You never do**, not through
hostcare `run`, not "just apt update", not a reboot. If you catch yourself about to run `sudo`, `apt install`, `dpkg`, `dkms install`, `reboot` or
anything that changes packages, stop: print it for the owner. The tool refuses these too. hostcare's never list refuses, whatever was approved, every
command or note that contains `reboot`, `shutdown`, `poweroff`, `halt`, `passwd`, `.env`, `credentials`, `rm -rf` and the other words it lists
(`aibridge/ops/hostcare/hostcare_mcp.py`, NEVER): **never write those words into a command, a log step or a note**. Say "restart" instead.

The procedures live in `gpu-host/upkeep/` on the GPU host (read `UPKEEP.md` there for the details); the tool is
`python3 gpu-host/upkeep/upkeep.py`. Run its commands through hostcare's `run(command, reason)` (level 2: the operator approves each one). Every
command below is no-root; `--apply` is only for busy on/off, snapshot, verify and log lines, and without it everything prints and changes nothing.

- **Where to run it.** The plan's second line says `run from the bridgeai checkout: cd PATH`. hostcare starts in the home directory, so write every
  command as `cd PATH && python3 gpu-host/upkeep/upkeep.py ...` with that PATH (it comes from the tool, not from a person).
- **Timeouts.** `run` stops after 120 s by default and 300 s at most. Pass `timeout=300` for `verify`, `unlock --run --apply` and `snapshot`. The tool stops its own selfcheck at 240 s (`incomplete`:
  the gate stays closed, run it again when the card is free). Exit code 124 means "timed out: run it again", not "failed". The claim "the busy switch always goes back to closed" **does not hold on a
  SIGKILL** (hostcare's kill at its timeout): a `finally` cannot run then. What holds: the tool leaves a marker before it opens the gate for the selfcheck, and **the next upkeep call of any kind**
  (`idle`, `busy status`, a plan, `verify`) closes the gate again and prints `RECOVERED` on stderr. If you see `RECOVERED`, tell the owner at once (a verify was killed; the gate is closed; the
  driver is not verified) and run `verify --to NEW --apply` again when the card is free. After any exit 124 of a verify, run `busy status` and say what it prints.
- **One state directory.** The snapshots and the audit log live in `UPKEEP_STATE_DIR` (default `~/.local/state/bridgeai-upkeep`, per account). The owner's
  account and yours must use the same directory, or a rollback run by the owner finds no snapshot. Ask the operator to set it for both.

## When an update is due

- `gateway gpu status` and the gate's `driver_watch` say what is available and its class. **Security**: do it now, as soon as the card is free; do not
  wait for a measurement. **Performance, feature or unknown class**: do it only if it unlocks a measured gain; plan it, but the last step is the bench
  and the rule is "keep it only if nothing is slower or costlier". A kernel-only update, a container toolkit or a `gpu-unlock` version follows the same care
  (UPKEEP.md, "Adding a procedure": only the driver procedure is built today; for the others say that, and give the generic steps of `driver_watch.py status`).
- Never update because a version is newer. Update because a bulletin fixes something that affects this host, or because it measures better.

## Tell people first

The card goes out of rotation: the stacks use the next host, and jobs wait or move. Before the window, tell the people who use the GPU host (and the owner)
when and for how long, in **their** language (Spanish, Russian or English: follow the person, not this file). Say it plainly: "the GPU is unavailable from X to
about Y for a security update; nothing is lost, jobs wait or go to another machine". Do not start while a person is on the card (`idle` says so).

## The procedure

1. **Plan.** `python3 gpu-host/upkeep/upkeep.py plan driver --to VERSION` (VERSION is digits and dots, like 595.112.07: anything else is refused).
   Read the PREFLIGHT first. With a `NOT OK` the tool prints **no steps**, and neither do you:
   - `NOT OK repo` alone (the version is not in the package lists): the lists may be stale. Have the owner run `sudo apt update`, then plan again.
     If it is still not offered, stop and tell the operator.
   - any other `NOT OK` (`/boot` too small, no gate token, wrong pin count, a target that is not newer): stop, say why, ask the operator.
   `wait` is fine: it means something runs and the steps wait for it. Show the owner the steps; explain in two lines what each owner step is for.
   The steps are tagged `[owner, root]` (the owner runs it as root), `[owner, no root]` (the owner runs it as themselves: the simulations) and
   `[bot, no root]` (yours).
2. **Close the gate and snapshot** (you, `--apply`): `busy on --apply`, `idle` until it says `idle: yes`, `snapshot --apply`. The snapshot is the rollback;
   never skip it. If `idle` stays "no" for long, say what runs and wait; never kill a job. A `snapshot REFUSED` means the host is not in a clean state
   (a half-updated one): do not use `--force` on your own; say why and ask the operator.
3. **Ask the owner to run, in this order, one transaction at a time**: `sudo apt update`; then the **pin alone** (`sudo apt install nvidia-driver-pinning-NEW`, plus the
   container toolkit if the plan says so). The pin and the driver packages are **two** transactions: apt reads the old pin at the start of a transaction, so one
   command with both leaves the old driver ("already the newest version"). Never offer them as one command. Ask only whether apt ended without errors.
4. **The simulations (the owner runs them; you never run `apt`, and you never put text a person pasted into a command).** Before each transaction the plan prints a
   simulation for the owner: the pin (`check-sim - --pin --to NEW`) and the driver packages (`check-sim - --to NEW`). Two ways to hand you the answer:
   - the owner runs the printed pipe and reads you the first line, `check-sim: ok (target X)` or `check-sim: not ok (target X)`, with the reasons; or
   - the owner writes the simulation to the file the plan prints (`apt install -s ... > FILE 2>&1`) and you run `check-sim FILE --to NEW` (FILE is the path
     the plan printed, made only of letters, digits and `/ . _ -`; if it is anything else, ask for another). The tool reads the file as data.
   Never run `check-sim -` with pasted text, never build a heredoc or `echo` from what someone typed to you, never copy apt output into a command or a note.
   `ok`: the owner may apply. `not ok`: **do not let them apply**; give the reason in plain words. "pin not swapped" means the pin step was not done alone (or not
   done): repeat step 3. "removes X" (anything but the old pin) or "does not cover N driver package(s)" or a protected package (gpu-unlock, the running kernel) is a
   stop: say so and ask the operator. The tool refuses removals on purpose: `UPKEEP_ALLOW_REMOVE` lists an exception, and only the operator sets it.
5. **Owner applies** `sudo apt install --no-remove <driver packages>` (DKMS builds for minutes). Then `verify --to NEW --installed`. A FAIL (a kernel without the dkms
   build or headers, a package left behind) means **no reboot**: fix it or roll back.
6. **Owner reboots** in a quiet window. After the host is back: `verify --to NEW --apply`.
   - `RESULT: ok`: the gate is open again; tell the people the GPU is back, with the new version in one line.
   - `RESULT: degraded` (the unlock did not survive: the card is slower and costs more energy for the same work) or a FAIL: the gate stays closed and the
     rollback is printed. Show it to the owner; do not roll back on your own and do not leave it half-way. The owner decides (a security update may be worth
     keeping without the unlock; a performance update is not).
   - `RESULT: incomplete`: no verdict (the card was in use, selfcheck error). The gate stays closed; run it again when the card is free.
7. **Non-security update**: after `ok`, run the bench (`python3 gpu-host/bench_gate.py --recheck`, idle window) and compare with the earlier numbers. Slower or
   costlier: `rollback`.

## Rollback

`python3 gpu-host/upkeep/upkeep.py rollback [SNAPSHOT]` prints the way back from the snapshot, also in two transactions (the old pin alone, then
`--allow-downgrades` with the exact old versions), its own simulations (`check-sim --pin`, `check-sim --rollback-from SNAPSHOT`), the reboot and the verify.
Walk the owner through it the same way, with the same rules for the simulations. With a `NOT OK` (the old pin or an old version is not offered, a snapshot that cannot
be used) it prints no steps: if the lists may be stale have the owner run `sudo apt update` and run it again; otherwise say so and ask the operator. The
owner may drop the container toolkit packages from the line if only the driver is the problem. A rollback of a **security** update leaves the host exposed: say
that plainly, and the reason goes in the log.

## Keep the log

`upkeep.py log` is the append-only audit. The tool writes its own lines. You record what the owner did with
`log --add owner-apt-pin --result done --note "…" --apply` (steps: `owner-apt-update`, `owner-apt-pin`, `owner-apt-driver`, `owner-host-restart`; result `done` or
`failed` with the error in the note). The step names and the notes must not contain a word hostcare refuses (see the top: no `reboot`, `halt`, `passwd`…): hostcare
would refuse the whole command and the step would never be recorded. At the end give the owner a short summary: versions before and after, selfcheck verdict, what was
postponed. Never put a token, a key, a person's data or text copied from apt in a note.

## The card as a whole: what to re-bench, apply and undo

The same tool covers the rest of the NVIDIA card (UPKEEP.md, "GPU card management"). None of it needs root, and none of it is done without the owner's yes.

- **When to re-bench.** After a **driver**, an **unlock** (`gpu-unlock` version) or a **kernel** change the last bench no longer describes this host. `python3 gpu-host/upkeep/upkeep.py unlock` ends with
  `rebench: DUE (driver A -> B ...)` when that is so. Then, in an idle window: `python3 gpu-host/bench_gate.py --recheck`, record it with
  `log --add bench --result done --ref RUN --apply` (RUN is the bench's run id; the tool stores the driver, kernel and unlock it was measured on), and propose the numbers (next point).
- **Check the unlock.** `unlock` answers `ok`, `degraded` or `unknown` on its first line. `degraded` (the card is back to stock speed and costs more energy for the same work, or a DKMS build
  of nvidia or gpu-unlock is missing) is never hidden: tell the owner at once. `unknown` means it could not judge (no result yet, or a result for another driver or kernel): `unlock --run --apply`
  (`timeout=300`) measures now; it keeps the gate closed unless the verdict is ok.
- **Where the files are.** On a standard install the checkout and the deployed copy are the same files. `plan profile` and `plan deploy` therefore never default to a destination inside the checkout:
  without `--dest DIR` they say `NOT OK destination`. Take DIR from the tool's own message (it prints the `--dest` to use), say to the owner where the change will land, and copy `--dest DIR` into the
  apply command exactly as the plan prints it. Read the warnings to the owner before asking for the yes: `warn git` (a dirty tree and the files this deploy would revert to the source's copy),
  `warn profile` (the deploy overwrites measured values: run `plan profile` again afterwards) and `warn gate` (the gate does not run from or read these files). A `NOT OK` for a symlink
  (`--mcp-dispatch` or the destination) is for the owner to fix by hand: the tool never replaces a symlink, and you do not work around it.
- **Apply a bench proposal.** `plan profile` (no flags: the newest run of `~/bench_gate/results.jsonl`) prints the PREFLIGHT, the **diff** of `power_profiles.conf` (the card's power caps) and
  `gate/gate.py` (the VRAM needs), and a confirm id. Read the diff to the owner in their language: which service, from what to what, from which bench run, and that the gate restarts. `NOT OK`
  stops (typically: no section for the card, or the numbers are from another card): say why, do not edit files by hand. Only after the owner says yes:
  `plan profile --apply --confirm ID` with the id **from that dry run** (it changes if the results or files change). If it says a service runs: wait for idle, or ask the owner whether to add
  `--restart-while-running` (the gate adopts running services, nothing is cut) or `--no-restart`; **never add either on your own**, and the same for `--allow-lower-need` (a VRAM need that falls by
  more than 25%: the owner's word only).
- **Deploy new gate code.** `plan deploy --from-ref REF` (a commit of the checkout) or `--from-dir DIR`: the same dry run, counts, `gate.py`'s md5 before and after, confirm id; the host's own
  data (`host.env`, `state/`, logs, `out/`, `models/`) is never touched. Apply only with the owner's yes: `plan deploy ... --apply --confirm ID`. A gate that does not come back is rolled back by
  the tool itself; tell the owner.
- **Roll back.** `undo` lists the changes that have a backup; `undo ID --apply` restores them exactly (md5 checked) and restarts the gate by the same rules. If it says a file was changed
  after the change, stop: that is a later change or a hand edit; `--force` only on the owner's word. Rolling back a profile or a deploy needs no root; a driver or kernel rollback is the
  procedure above.
- **Kernel update.** `plan kernel` is print-only. The rule that matters: `unlock --kernel RELEASE` must say `ok new kernel` **before** the owner restarts the host (nvidia and gpu-unlock are
  built for the new kernel); a FAIL means no restart. The owner's simulation of the kernel packages is read with `check-sim - --kernel --to RELEASE` under the same rules as the driver's
  (a file or the one-line verdict, never pasted text in a command). After the restart: `unlock --run --apply`, then re-bench and `plan profile`.
- **The record.** Every change writes a before line and an after line; `log --history` prints them with the md5 or versions, the bench reference and the rollback command. Those events stay on
  the host (the state directory): never copy them into a repository, a document or a message to someone else.

## Never

- Run a root step, or a command that changes packages, units, the boot line or power. The owner runs it; you print it.
- Merge the pin and the driver packages into one `apt install`, or skip `check-sim`, or apply a simulation that is `not ok`, or put pasted text into a command.
- Reboot, or ask for one, while the gate is open or a job is running; or open the gate after a `degraded` or `incomplete` verify.
- Show or ask for a token, a `host.env` or any key. The gate token is read by the tool and never printed.
- Update a host that is not the one the owner named, or a client machine (level 0 only there).
- Say it worked without `verify` having said `RESULT: ok` (or, for a profile, a deploy or an undo, the tool's `RESULT: ok`; `degraded` is not ok).
- Apply a profile or a deploy without the owner's yes, with a confirm id that did not come from the dry run you just showed, or add `--restart-while-running`, `--no-restart`, `--allow-lower-need` or `--force` on your own.
- Put an environment variable in front of an upkeep command, any `UPKEEP_*` one (`UPKEEP_ALLOW_REMOVE`, `UPKEEP_PROTECT`, `UPKEEP_GPU_DIR`, `UPKEEP_STATE_DIR`, `UPKEEP_BOOT_DIR`, `UPKEEP_BOOT_MIN_MB`,
  `UPKEEP_CHECKOUT`, `UPKEEP_SELFCHECK`, `UPKEEP_TEST`, ...): only the operator sets those, in the account's environment. `UPKEEP_TEST`, `UPKEEP_SELFCHECK` and `UPKEEP_CHECKOUT` belong to the selftest
  alone (the tool ignores them without the selftest's marker file, and says `IGNORED`). The tool prints and logs an `OVERRIDE` when one is set, and the owner who approves your command sees it.
- Create, move or delete files in the state directory (`verify-in-progress.json`, `audit.jsonl`, `backups/`), or a file named `upkeep-selftest.marker`: they are the tool's safety nets, and a marker
  the tool did not write is never evidence of anything.
- Edit `power_profiles.conf`, `gate.py` or the deployed tree by hand, or copy files into it: the tool backs up, checks and can undo; a hand edit has no backup.
