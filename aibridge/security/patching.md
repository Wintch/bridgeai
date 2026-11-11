---
title: Patching and vulnerability management
scope: Debian/Ubuntu servers and guests, Docker images
when_to_use: a CVE/KEV is announced; a scanner reports findings; planning a patch window; apt left something half-configured
related: [README.md, policies.md]
---
# Patching and vulnerability management

Patch in two separable steps: install packages without rebooting (fast, low risk, closes most deadlines), then reboot or restart on a schedule. Prioritize by known exploitation and exposure, test on one machine first, roll the rest one at a time, and verify that the fixed code is the code actually running. Scanners (Vuls, Trivy) find work; they do not prove it is done.

## Quick decision table

| Situation | Do | Rule |
|---|---|---|
| New CVE announced, unsure how urgent | Check KEV listing and whether the service is reachable from outside | SEC-PATCH-1 |
| "0 packages upgradable" | Run `apt-get update`, then count again | SEC-PATCH-2 |
| KEV deadline in days, host cannot reboot now | Install packages now, no reboot; reboot later in a window | SEC-PATCH-3 |
| Upgrading a guest through the hypervisor's guest agent | Launch apt with `systemd-run --no-block`, poll a marker file | SEC-PATCH-4 |
| `dpkg --audit` prints anything | `dpkg --configure -a` as a separate systemd unit | SEC-PATCH-5 |
| Kernel upgrade on a machine with a small `/boot` | Check free space first, abort under threshold | SEC-PATCH-6 |
| Script run via guest exec uses `<(...)` or `[[ ]]` | Use `bash -c`, not `sh -c` | SEC-PATCH-7 |
| Many similar guests to patch | Canary one, then roll one at a time with a post-check | SEC-PATCH-8, SEC-PATCH-9 |
| Want automatic patching on a desktop or workstation | Security-only unattended-upgrades, no auto-reboot | SEC-PATCH-12 |
| Package installed but unsure it is live | `needrestart`, `reboot-required`, check mapped libraries | SEC-PATCH-13, SEC-PATCH-14 |
| Vuls says vulnerable but the distro already patched | Likely a backport false positive | SEC-PATCH-16 |
| Third-party PHP build (Sury/ondrej) on Ubuntu | Scanner is blind; check changelog by hand | SEC-PATCH-16, SEC-PATCH-19 |
| Docker image scan | `trivy image` on the built image, `--ignore-unfixed` | SEC-PATCH-17 |
| Rebuilt image still shows old OS packages | Cached apt layer; change the refresh build ARG | SEC-PATCH-18 |
| Patch window finished | Write down what, where, when, what is still pending | SEC-PATCH-20 |

## Rules

### SEC-PATCH-1: Prioritize by KEV and exposure, not CVSS alone
- **Rule:** Rank work by (1) listed in the CISA KEV catalog (known exploited) and its due date, (2) whether the vulnerable service is reachable from untrusted networks, (3) whether a fixed package exists, and only then (4) CVSS score.
- **Why:** CVSS measures severity in the abstract. A medium CVE with public exploitation on an internet-facing service is more urgent than a critical in a library nothing exposes. KEV gives a hard date.
- **How:**
  ```bash
  # Pull the KEV catalog and match against your scanner output
  curl -s https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json -o kev.json
  jq -r '.vulnerabilities[] | [.cveID,.dueDate,.product] | @tsv' kev.json | grep -F <CVE-ID>
  ```
  Order of work: KEV + exposed first; KEV + internal second; non-KEV criticals with a fix third; the rest in the normal cycle.
- **Verify:** Every KEV item on the fleet has an owner and a date before the KEV due date.
- **Don't:** Sort a report by CVSS and start at the top. Do not treat findings with no available fix as patchable (list them separately as "no fix", with a mitigation or a replacement plan).

### SEC-PATCH-2: Refresh apt lists before concluding anything
- **Rule:** Run `apt-get update` before counting upgradable packages or declaring a machine up to date. Record the age of the lists when reporting.
- **Why:** With stale lists, `apt-get -s upgrade` reports "0 upgradable" even when dozens of security updates exist. Parked, rotated-out or never-auto-updated machines have lists that are months old.
- **How:**
  ```bash
  apt-get update -qq
  apt list --upgradable 2>/dev/null | grep -c '\['
  apt list --upgradable 2>/dev/null | grep -c -- '-security'
  # age of the lists in days
  echo $(( ( $(date +%s) - $(stat -c %Y /var/lib/apt/lists/partial) ) / 86400 ))
  ```
- **Verify:** The report states how fresh the lists were. A count of zero after a successful `update` is trustworthy; a count of zero without `update` is not.
- **Don't:** Rely on a machine's own auto-update to have run. Check that the timer or cron actually ran.

### SEC-PATCH-3: Install packages first, reboot separately
- **Rule:** Split every patch into phase A (install packages, no reboot, no disruption) and phase B (reboot or restart to load kernels, QEMU, daemons). Phase A can run in business hours; phase B is scheduled.
- **Why:** Most KEV deadlines are met by phase A alone. Reboots cost availability and carry their own risk, so they should not be coupled to a deadline unless the fix is in the kernel.
- **How:**
  ```bash
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get -s full-upgrade | grep -E '^(Remv|Inst)' | head -50   # simulate: nothing unexpected removed
  apt-get -y -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef full-upgrade
  ```
  Use `--force-confold` whenever local config files are customized (monitoring agent, lvm, repo sources), so no prompt blocks the run and local config survives. Review `*.dpkg-dist` files afterwards.
- **Verify:** Exit code 0, `dpkg --audit` empty, `apt list --upgradable` empty, then see SEC-PATCH-13 for what still runs old code.
- **Don't:** Pipe the run into a pager or prompt. Do not remove packages the simulation did not announce. Do not reboot in the same step.

### SEC-PATCH-4: Run long package jobs outside the guest-agent cgroup
- **Rule:** When patching a VM through the hypervisor's guest agent (`qm guest exec` or equivalent), start apt as its own transient systemd unit and poll a marker file for the result.
- **Why:** A command launched by the agent lives in the agent service's cgroup. If the upgrade includes `qemu-guest-agent`, its postinst restarts the service and systemd kills the whole cgroup, including the running dpkg. Also, the exec call can time out or return non-JSON while the job finishes fine, so its return value is not the result.
- **How:**
  ```bash
  qm guest exec <vmid> --timeout 40 -- bash -c '
    rm -f /var/log/apt-job.last
    systemd-run --unit=apt-job --collect --no-block bash -c "
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get -y -o Dpkg::Options::=--force-confold full-upgrade > /var/log/apt-job.log 2>&1
      echo rc=\$? > /var/log/apt-job.last"'
  # poll later
  qm guest exec <vmid> --timeout 20 -- bash -c 'cat /var/log/apt-job.last 2>/dev/null'
  ```
- **Verify:** `/var/log/apt-job.last` contains `rc=0`; then SEC-PATCH-5. If the file is absent, apt is still running: wait, do not start a second one.
- **Don't:** Run `apt-get` in the foreground of an agent exec. Do not kill a running dpkg because it is slow on a saturated disk (apt jobs over 30 minutes happen on busy storage). Do not trust the exec return code over the log.

### SEC-PATCH-5: Make `dpkg --audit` a standard verification, repair outside the cgroup
- **Rule:** After every package run, execute `dpkg --audit`. Empty output means clean. If it prints anything, finish configuration with `dpkg --configure -a` as a separate systemd unit.
- **Why:** An interrupted dpkg leaves packages "unpacked" or "half configured" and pending triggers (initramfs, libc, systemd). Retrying the same command inside the same cgroup reproduces the kill.
- **How:**
  ```bash
  dpkg --audit
  systemd-run --unit=dpkg-fix --no-block env DEBIAN_FRONTEND=noninteractive dpkg --configure -a
  systemctl show dpkg-fix -p Result -p ExecMainStatus -p ActiveState
  dpkg --audit            # must print nothing
  ```
- **Verify:** `Result=success`, `ExecMainStatus=0`, `ActiveState=inactive`, `dpkg --audit` empty.
- **Don't:** Reboot a machine with a non-empty `dpkg --audit`, especially after a kernel install: the initramfs may be missing or truncated.

### SEC-PATCH-6: Check `/boot` space before kernel upgrades and repair in order
- **Rule:** On machines with a separate, small `/boot`, check free space before installing a kernel, abort under a threshold, and if it already failed repair in a fixed order.
- **Why:** Each new initramfs is written while the old ones still exist. Large initramfs images (hundreds of MB, for example with GPU firmware) fill `/boot`, leave initramfs-tools half done, and the machine can fail to boot.
- **How:**
  ```bash
  # Pre-check: abort if /boot has less than ~600 MB when a kernel is upgradable
  mountpoint -q /boot && apt list --upgradable 2>/dev/null | grep -q '^linux-image-' && \
    [ "$(df -Pm /boot | awk 'NR==2{print $4}')" -ge 600 ] || echo "ABORT: free /boot first"
  ```
  Repair order when `/boot` is already full:
  1. Remove the initrd of the **oldest** installed kernel (regenerable). Never the running one, never the new one.
  2. Confirm at least ~330 MB free, then `dpkg --configure -a`.
  3. Verify the new initrd: readable with `lsinitramfs`, size within about 80% of the running one, contains `lib/modules/<new-kernel>/`, `dpkg --audit` empty.
  4. Only then purge the old kernel packages and run `update-grub`.
  5. If out-of-tree modules (DKMS, GPU drivers) are used, confirm they exist for the new kernel before rebooting.
- **Verify:** `df -h /boot`, `ls /boot | grep -E 'vmlinuz|initrd'`, GRUB config has an entry with the new initrd, `dkms status` shows the module installed for the new kernel.
- **Don't:** Reboot until step 3 passes. Do not purge the old kernel before the new one is verified.

### SEC-PATCH-7: `sh` is dash in guest-exec scripts
- **Rule:** Wrap scripts sent through guest exec or a remote one-liner in `bash -c`. Do not assume bash features under `sh -c`.
- **Why:** On Debian and Ubuntu `/bin/sh` is dash. Process substitution `<(...)`, `[[ ]]`, arrays and `$'...'` fail or behave differently.
- **How:** Prefer `qm guest exec <vmid> -- bash -c '...'`. If a collector must stay portable (read-only inventory), write it in POSIX sh deliberately and test it with `dash`.
- **Verify:** `dash -n script.sh` for POSIX scripts; run once on a throwaway guest.
- **Don't:** Mix both styles in one payload.

### SEC-PATCH-8: Canary one machine before rolling
- **Rule:** Apply the full procedure (packages, reboot if needed, post-check) to one low-risk machine of the group first. Wait for its result before touching the others.
- **Why:** A changed hypervisor, QEMU minor version, kernel or a package with a bad postinst shows up on the first machine. The canary is also where you measure real duration.
- **How:** Pick a machine that is representative but replaceable. Use the same script you will roll with. Capture before/after: kernel, pending count, `dpkg --audit`, `systemctl --failed`, service-specific health, and a settling period (for example 60 seconds plus a second check).
- **Verify:** The canary is healthy after the settling period, with the same service counters as before.
- **Don't:** Skip the canary because the hosts "look the same". Do not reboot the hypervisor if the canary guest failed to come back healthy on the new QEMU.

### SEC-PATCH-9: Roll guests one at a time with a post-check and a stop condition
- **Rule:** Process guests sequentially. Before each: confirm the previous one is healthy and shared resources (disk I/O pressure) are normal. After each: compare health with the pre-state. Stop the whole run on the first failure.
- **Why:** Parallel patching on shared storage causes iowait storms and masks which guest broke. Stopping early keeps a failure at one machine.
- **How:** A roll script should (a) read pre-state and refuse to start if it is unhealthy, (b) start apt via SEC-PATCH-4, (c) refuse to reboot if rc is not 0 or `dpkg --audit` is not empty, (d) `qm reboot`, wait with a timeout, compare service counters, (e) re-check after about 60 seconds, (f) pause automation that would restart or stop guests meanwhile (a rotation scheduler, for example) with a pause file and remove it afterwards. Gate each guest on disk pressure:
  ```bash
  head -1 /proc/pressure/io     # require avg60 below ~60 before starting the next guest
  ```
- **Verify:** After each guest: `systemctl is-system-running` is `running`, failed units 0, `dpkg --audit` empty, pending 0.
- **Don't:** Launch a stagger shorter than the disk can absorb (13 simultaneous apt runs on one HDD drove load to ~6x core count). Do not forget to remove the pause file.

### SEC-PATCH-10: Retired
- **Retired:** hypervisor material that is not part of bridgeai. The ID stays reserved.

### SEC-PATCH-11: Retired
- **Retired:** hypervisor material that is not part of bridgeai. The ID stays reserved.

### SEC-PATCH-12: Security-only unattended-upgrades, kernel held, no auto-reboot
- **Rule:** On workstations and standalone servers, enable automatic updates for the security origin only, exclude kernel and headers, disable automatic reboot, and set needrestart to list-only.
- **Why:** Automatic security fixes shrink the exposure window between your manual rounds. Kernels need a reboot and, on small `/boot`, can fill it (SEC-PATCH-6). needrestart in automatic mode restarts services such as the display manager or network manager.
- **How:**
  ```
  // /etc/apt/apt.conf.d/52unattended-upgrades-local
  #clear Unattended-Upgrade::Origins-Pattern;
  Unattended-Upgrade::Origins-Pattern {
          "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";
  };
  Unattended-Upgrade::Package-Blacklist { "linux-image-.*"; "linux-headers-.*"; "linux-kbuild-.*"; };
  Unattended-Upgrade::Automatic-Reboot "false";
  Unattended-Upgrade::Remove-Unused-Kernel-Packages "false";
  Dpkg::Options { "--force-confdef"; "--force-confold"; };
  ```
  ```
  // /etc/apt/apt.conf.d/20auto-upgrades
  APT::Periodic::Update-Package-Lists "1";
  APT::Periodic::Unattended-Upgrade "1";
  ```
  ```
  # /etc/needrestart/conf.d/90-unattended.conf
  $nrconf{restart} = 'l';
  ```
  Dry run before trusting it: `unattended-upgrade --dry-run -v`.
- **Verify:** `apt-config dump | grep Unattended-Upgrade`, `systemctl list-timers apt-daily-upgrade.timer`, then read `/var/log/unattended-upgrades/unattended-upgrades.log` after the first run.
- **Don't:** Enable it on production guests that have their own staged roll. Do not let it pull kernels. Adjust the origin pattern for Ubuntu (`${distro_id}ESM`/`-security` origins); the one above is Debian-specific.

### SEC-PATCH-13: Find out what still runs old code
- **Rule:** After installing, list services and processes that still use replaced files, and whether a reboot is pending. Report both.
- **Why:** An updated library does not fix a process that mapped the old one. A kernel update does nothing until reboot.
- **How:**
  ```bash
  test -f /var/run/reboot-required && cat /var/run/reboot-required.pkgs
  needrestart -r l -b            # list only; add -k for kernel check
  uname -r; ls /boot/vmlinuz-* | sort -V | tail -1   # running vs newest installed
  ```
  Where needrestart is not installed, use the library check in SEC-PATCH-14.
- **Verify:** Services in the list are restarted deliberately (one at a time, with health checks), then the list is empty.
- **Don't:** Let needrestart restart services automatically on production. Do not treat `reboot-required` as authoritative for hypervisor kernels or QEMU (it may not be set); compare versions instead.

### SEC-PATCH-14: Verify the patched version is the one loaded
- **Rule:** "Installed" is not "fixed". Confirm the running process uses the new binary or library.
- **Why:** Daemons keep old code until restarted. Some services (for example nginx run by a supervisor, or php-fpm masters) are not restarted by package scripts.
- **How:**
  ```bash
  # processes still mapping a deleted (replaced) library or binary
  # (memfd:, /dev/zero and SYSV entries are shared memory, not old code: filtered out)
  for m in /proc/[0-9]*/maps; do
    f=$(grep ' (deleted)$' "$m" 2>/dev/null | grep -v -e '/memfd:' -e '/dev/zero' -e '/SYSV' | awk '{print $6}' | sort -u | head -1)
    [ -n "$f" ] && p=${m#/proc/} && p=${p%/maps} && echo "$p $(cat /proc/$p/comm 2>/dev/null) $f"
  done
  ls -l /proc/<pid>/exe                         # "(deleted)" means old binary still running
  <service> -v; apt-cache policy <package>      # version on disk vs candidate
  ```
  For hypervisors: the running QEMU version of a guest changes only when that guest is restarted (stop/start or `qm reboot`), not on package install.
- **Verify:** No process maps the old file, version reported by the running service equals the fixed version, changelog of the package mentions the CVE.
- **Don't:** Count a PHP-FPM `/dev/zero (deleted)` mapping as an old binary: that is opcache shared memory. Do not treat the version printed by the binary on disk as proof for the daemon already running.

### SEC-PATCH-15: Use Vuls as an agentless, weekly, fast-mode inventory
- **Rule:** Scan the fleet with Vuls weekly in fast mode over SSH (or from a package list collected by guest exec), keep the CVE database refreshed nightly, and summarize per host only the findings that have a fix.
- **Why:** It gives a package-level CVE view across hosts with no agent. The database is built nightly, so a CVE published today appears tomorrow. Cutting to `-ignore-unfixed` keeps results small and actionable.
- **How:**
  ```bash
  vuls scan -config=config.toml                       # fast scan over SSH, no root needed
  vuls report -config=config.toml -ignore-unfixed -format-one-line-text
  # for guests without SSH: collect read-only (os-release, uname, dpkg-query) via the hypervisor,
  # POST to a local `vuls server`
  ```
  Keep the DB on a disk that cannot fill up or be filled by something else. Results are about 10-15 MB per host with `-ignore-unfixed`, over 100 MB without. Keep the reboot-pending flag from your own collector, since Vuls does not know it.
- **Verify:** Each host has a result newer than the DB date; the summary shows host, OS, KEV count, fixable count, reboot-pending, and a "blind" flag (SEC-PATCH-16).
- **Don't:** Run a scan right after a CVE is published and read an empty result as "not affected". Do not let a timed-out DB update leave a half-written database: a retry may start a full re-download.

### SEC-PATCH-16: Know the blind spots and false positives of the scanner
- **Rule:** Treat Vuls output as incomplete. List what it cannot see, and handle those items by other means.
- **Why:**
  - Third-party PHP builds (Sury/ondrej) on **Ubuntu**: the distro publishes no advisories for them, so the package is not evaluated. On Debian it is evaluated per source package.
  - Static binaries (embedded PHP runtimes, Go binaries), Docker images, shared-hosting panels, and hosts reachable only through an agent channel are not covered.
  - NVD version ranges can flag a package as vulnerable when the distro backported the fix without changing the upstream version number.
  - End-of-life operating systems get "no fix available" findings that no update will close.
- **How:** Mark such hosts "blind" in the summary, then check by hand: `apt changelog <package> | grep <CVE>` or the package changelog under `/usr/share/doc/<package>/`, the vendor's advisory page, and the running version (SEC-PATCH-14). Scan images with Trivy (SEC-PATCH-17).
- **Verify:** Each blind or contested item has a manual verdict recorded with the evidence (changelog line, version).
- **Don't:** Declare a host clean because the scanner printed nothing for a package family it does not support. Do not "fix" a backport false positive by upgrading to a non-distro version.

### SEC-PATCH-17: Scan the built image with Trivy, fixed-only, long timeout
- **Rule:** Scan the image you will deploy (not the Dockerfile), count only vulnerabilities that already have a fix, and use a generous timeout.
- **Why:** The image contains the layers that matter, including cached ones. Findings without a fix are noise for the acceptance decision. Large images exceed short timeouts and produce partial or no output.
- **How:**
  ```bash
  docker run --rm -v /var/run/docker.sock:/var/run/docker.sock:ro -v trivy-cache:/root/.cache \
    aquasec/trivy:latest image -q --scanners vuln --ignore-unfixed --severity HIGH,CRITICAL \
    --skip-version-check --timeout 30m <image>
  ```
  Scan the local image store, not only the running containers (same images, easier to script). Findings in `linux-libc-dev` (kernel headers) are noise in a container. The scan does not cover secrets, container configuration, permissions, and sees Go binaries without package metadata poorly.
- **Verify:** Acceptance criterion: zero CRITICAL findings with a fix available in the images you own. Record the HIGH count to track drift.
- **Don't:** Judge by the total count with unfixed findings included. Do not leave the scanner image, its cache or scan output on production machines afterwards.

### SEC-PATCH-18: Rebuild images so the OS layer is really refreshed
- **Rule:** Force the OS package layer to re-run on purpose, pin base images by digest and refresh the pin, bump application dependencies that apt does not manage, and keep a rollback tag.
- **Why:** Docker caches the `apt-get` layer until its inputs change; a rebuild with no change reuses old packages and the scan looks identical. A tag like `node:24-bookworm-slim` moves upstream, so a digest pin gets stale. `pip` and `npm` dependencies (image libraries, HTTP clients, JWT libraries) live outside apt, and some are pinned exactly by upstream projects.
- **How:**
  ```dockerfile
  ARG SECURITY_REFRESH=<YYYY-MM-DD>          # change this date to bust the cached apt layer
  RUN echo "$SECURITY_REFRESH" >/dev/null && apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/*
  FROM node:24-bookworm-slim@sha256:<digest>   # pin by digest; re-check what the registry serves now
  ```
  ```bash
  docker tag <image>:latest <image>:prev-$(date +%F)     # before the rebuild
  docker build --pull --build-arg SECURITY_REFRESH=$(date +%F) -t <image>:latest .
  docker rmi <image>:prev-<oldest>                        # keep the last ~4 prev-* tags
  ```
  Inside the image: `pip list --outdated`, `npm ls <package>` to find copies outside apt, and note exact upstream pins that only move with the upstream version. Moving the base to the next OS release gives the largest reduction in findings and the largest compatibility risk: do it on a separate tag, run the self-tests, then decide.
- **Verify:** Re-run Trivy (SEC-PATCH-17); a periodic audit flags images older than N days, a refresh date older than N days, a base digest differing from the registry, and too many `prev-*` tags. Rollback: retag `prev-<date>` as `latest` and recreate the containers.
- **Don't:** Assume `--no-cache` on every build is needed (slow, hides the real problem). Do not override an exact upstream pin inside the image: that creates an untested combination. Docker engine/containerd package upgrades on the host restart every container, so schedule them in the same window as the rebuild to avoid two outages.

### SEC-PATCH-19: Use third-party repositories as a bridge with an expiry date
- **Rule:** A third-party package source (for example the ondrej/sury PHP repositories) may be used to get a fix before a distro upgrade, but record an expiry and re-check that the source is still alive before relying on it.
- **Why:** These sources drop old distro releases soon after the distro's standard support ends, and then stop receiving fixes. The scanner may also not see them (SEC-PATCH-16).
- **How:**
  ```bash
  curl -s https://ppa.launchpadcontent.net/<owner>/<ppa>/ubuntu/dists/<series>/Release | grep -E '^Date'
  # confirm the fix is really in the build: read the changelog of the source package
  apt changelog <package> | grep -m3 <CVE-ID>
  ```
  Use the bridge to move from an EOL release to a supported one without changing the language version (jammy keeps the same PHP minor versions), then plan the real upgrade.
- **Verify:** The Release `Date` for the series is recent; changelog mentions the CVE; running pools restarted (SEC-PATCH-14).
- **Don't:** Treat the bridge as a destination. Do not assume a dead series (a Release date more than a year old) still gets patches.

### SEC-PATCH-20: Record what was done, when, and what is still pending
- **Rule:** At the end of every window, write a short record: machine, date, packages or versions before/after, commands or script used, exit codes, verification results, reboot state, rollback available, open items.
- **Why:** Reboot state and "installed but not loaded" are easy to lose; the next person (or assistant) needs them to avoid redoing or skipping work. Audit and deadline reporting depend on it.
- **How:** Keep a log file on the machine (`/var/log/<job>.log`, marker file with `rc=`), store the list of pre-change package versions when a change is risky (`dpkg-query -W > /root/pre_<date>.pkgs`), and add one line per machine to the team's patch log with: date, status (`patched, reboot pending` / `patched and rebooted` / `deferred, reason`).
- **Verify:** A reader can answer "is machine X exposed to CVE Y today?" from the record alone.
- **Don't:** Write only "patched". Do not store secrets, internal addresses or credentials in a shared record; reference machines by role or ID.

## Checklist for a patch window

1) Prioritize: KEV and exposure first; confirm fixes exist (SEC-PATCH-1).
2) `apt-get update` everywhere; list pending counts and list age (SEC-PATCH-2).
3) Back up host configuration and list pre-change versions off the machine (SEC-PATCH-20).
4) Check `/boot` space where a kernel is pending (SEC-PATCH-6).
5) Pause automation that starts/stops guests (SEC-PATCH-9).
6) Canary one machine; wait for a settled healthy result (SEC-PATCH-8).
7) Install packages without reboot, via a separate systemd unit, with `--force-confold` (SEC-PATCH-3, SEC-PATCH-4).
8) Verify: exit code, `dpkg --audit` empty, nothing pending (SEC-PATCH-5).
9) Roll the rest one at a time with post-checks; stop on first failure (SEC-PATCH-9).
10) Check what still runs old code; restart or reboot on schedule (SEC-PATCH-13, SEC-PATCH-14).
12) Rebuild and rescan images; accept at zero fixable criticals (SEC-PATCH-17, SEC-PATCH-18).
13) Re-run the scanner the next day, after the CVE database updates (SEC-PATCH-15).
14) Remove pause files and temporary units; delete scanner images and outputs.
15) Write the record (SEC-PATCH-20).

## Glossary

- **KEV:** CISA Known Exploited Vulnerabilities catalog. Listing means exploitation in the wild; each entry has a due date.
- **Backport:** A distro fix applied to an older upstream version without changing the upstream version number. Scanners that compare version ranges can misreport it as vulnerable.
- **Canary:** The first machine patched on its own, used to detect problems before the rest are touched.
- **cgroup kill:** systemd stops every process in a service's control group when the service restarts. A job started through a service (such as the guest agent) dies if that service restarts mid-job. Avoid with `systemd-run`.
- **Fast scan (Vuls):** SSH scan without root that reads package lists only, no deep inspection.
- **Unfixed finding:** A CVE with no published fixed version; excluded with `--ignore-unfixed` for acceptance decisions and tracked separately.
- **Marker file:** A file such as `/var/log/<job>.last` containing `rc=<code>`, written when a background job ends, so the result does not depend on the launching session.
