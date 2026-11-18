---
title: Backups and storage (verified copies, backup disks, cold storage, virtual disk cache)
scope: Proxmox VE hypervisors and guests, large backup copies to external or USB/SATA disks, offline backup disks, virtual disk cache and readahead on HDD/btrfs/xfs hosts
when_to_use: copying a VM or a large dataset to a backup disk; a backup disk is slow, hangs or reports errors; planning offline (cold) backups; backups are bigger than the data; an old VM copy exists on another host; choosing cache=none/writethrough/writeback or readahead for VM disks
related: [README.md, storage-performance.md, policies.md, patching.md, detection-and-audit.md, containers-and-images.md]
---
# Backups and storage

A backup is only as good as the last time someone read it back. Write it once, hash the stream at both ends, read the file completely after writing, and verify old copies on a rotation. Backup disks fail in ways SMART does not report, so configure them for backup use (bounded error recovery), throttle the copy so it does not starve production on the same disk, and stop on the first signs of damage. Related rules: off-VM backups and restore drills are in [containers-and-images.md](containers-and-images.md) (SEC-CONT-14); an attacker who controls the management plane can delete every copy that stays attached.

## Quick decision table

| Situation | Do | Rule |
|---|---|---|
| Copying a big backup to another machine or disk | Hash the stream at the source and the file at the destination | SEC-STOR-1 |
| The copy "finished without errors" | Read the whole file back and compare | SEC-STOR-2 |
| SMART says PASSED but reads crawl or the kernel logs I/O errors | Trust the attributes and the reads, not the verdict | SEC-STOR-3 |
| Backup disk hangs on a bad sector | Enable SCT ERC (bounded retries); disable it only to restore | SEC-STOR-4 |
| Many VMs to copy to one disk | One at a time, throttled, with stop conditions | SEC-STOR-5 |
| vzdump copies more than the real data | `fstrim` inside the guest before the backup | SEC-STOR-6 |
| `fstrim` through the hypervisor hangs in a vzdump hook | Talk to the guest-agent socket directly | SEC-STOR-7 |
| An old copy of a VM exists next to the live one | Never power it on with the same IP/MAC | SEC-STOR-8 |
| Backup disk stays disconnected most of the time | Monthly cycle, last-OK marker elsewhere, 30-day alert | SEC-STOR-9 |
| Old backups were never read again | Rotating verification of a slice every cycle | SEC-STOR-10 |
| Choosing the cache mode of VM disks | `none` unless measured otherwise; never `writethrough` on btrfs | SEC-STOR-11 |
| Tempted by `cache=writeback` | Know the power-cut risk; only for rebuildable data | SEC-STOR-12 |
| Host reads far more from disk than the VMs ask for | Lower `read_ahead_kb`, persist it by disk identity | SEC-STOR-13 |
| A disk "clicks" periodically | Read `Load_Cycle_Count` twice before assuming a failing head | SEC-STOR-14 |
| Disks run hot, many seeding VMs, btrfs write amplification, thermal throttle | See [storage-performance.md](storage-performance.md) | SEC-PERF-1 to 21 |

## Rules

### SEC-STOR-1: Hash the stream at the source and the file at the destination
- **Rule:** every large backup copy records a SHA-256 of the data as it leaves the source and a SHA-256 of the file as it is read from the destination disk. They must match before the copy counts.
- **Why:** a hash computed only at the destination proves nothing about transport; a hash taken from the data in flight proves nothing about what reached the platter. Two ends catch both. Copies through USB bridges, long pipes and flaky NICs corrupt quietly.
- **How:**
  ```bash
  # on the machine that runs the backup (bash): hash the stream while it is sent
  vzdump <vmid> --mode snapshot --stdout --compress zstd \
    | tee >(sha256sum | cut -d' ' -f1 > <dir>/<file>.src.sha256) \
    | ssh <backup-host> 'cat > <dest-dir>/<file>'
  # then on the backup host, from the disk (see SEC-STOR-2):
  sha256sum <dest-dir>/<file> | cut -d' ' -f1 | diff - <dir>/<file>.src.sha256 && echo OK
  ```
  Keep a note next to each file (date, source, what it is, hash). A `.notes` file per backup, written by a vzdump hook, is enough.
- **Verify:** corrupt one byte of a test copy and confirm the comparison fails.
- **Don't:** treat `rsync`/`scp` exit code 0 as verification; compare file sizes only.

### SEC-STOR-2: Read the whole file back after writing
- **Rule:** after each copy, read the full file from the destination and compare it with the source hash (SEC-STOR-1). Record the result as OK or UNREADABLE per file. A disk that writes fine can still fail to read.
- **Why:** a degraded disk accepts writes into its cache and spare areas and only fails when the data is read later, possibly months later when you need the restore. A file can be written without any error and still be unreadable at full speed past a few GB; the write path never reports it.
- **How:** for files smaller than the host's RAM drop the page cache first (`sync; echo 3 > /proc/sys/vm/drop_caches`) or the "read" comes from memory. Run the read as a background unit (`systemd-run --unit=<name> ...`) and keep a log; stop it with `kill <pid>` rather than `pkill -f <script>` over SSH (that pattern also matches, and kills, your own SSH session).
- **Verify:** every backup file has a logged OK from a read that took disk time (throughput close to the disk's real speed).
- **Don't:** declare "backup done" at the end of the write; verify only the newest file and assume the old ones.

### SEC-STOR-3: SMART "PASSED" is not a health verdict
- **Rule:** read the raw attributes and the actual read behavior of a backup disk, and treat uncorrectable sectors, a rising read-error rate and slow or hanging reads as failure even when the overall self-assessment says PASSED.
- **Why:** the overall verdict only flips at the vendor's thresholds, which sit far past useful. A large HDD can show PASSED with dozens of uncorrectable sectors, and then during a long read its raw read-error rate went from 0 to several thousand while throughput fell to a few hundred KB/s and the kernel logged "Internal target failure".
- **How:**
  ```bash
  smartctl -a /dev/disk/by-id/<disk-id>           # look at: Reallocated, Current_Pending, Offline_Uncorrectable, Raw_Read_Error_Rate, error log
  smartctl -t long /dev/disk/by-id/<disk-id>      # extended self-test; check the result later with -a
  dmesg -T | grep -iE 'ata|i/o error|target failure'
  ```
  Save a SMART snapshot at every backup cycle (SEC-STOR-9) so the trend is visible. Use stable names (`/dev/disk/by-id/...`), never `sdX`, which changes between boots and hot-plugs.
- **Verify:** a table per backup disk with date, uncorrectable count, pending count and read-error raw value; any increase is investigated before the next write.
- **Don't:** say "SMART is fine" from the one-line health result; keep the only copy of something on a disk with growing errors.

### SEC-STOR-4: Enable SCT ERC on backup disks; disable it to restore
- **Rule:** on a disk used for backups, set the error-recovery time limit (SCT ERC) to a few seconds every time the disk is connected. Turn it off only when restoring from a damaged disk.
- **Why:** without ERC a drive facing a bad sector retries without bound: reads look hung, `smartctl` itself stops answering, and a long job stalls for hours. With ERC at about 7 seconds the drive gives up on that sector, the kernel logs a real error, and the job (and your hash comparison) can report it. When you need to restore, the opposite is right: let the disk insist as long as it can on every sector (`scterc,0,0`).
- **How:**
  ```bash
  smartctl -l scterc /dev/disk/by-id/<disk-id>                 # show the current setting
  smartctl -l scterc,70,70 /dev/disk/by-id/<disk-id>           # 70 x 100 ms = 7 s for reads and writes
  smartctl -l scterc,0,0   /dev/disk/by-id/<disk-id>           # disable: for the restore of a damaged disk
  ```
  The setting is volatile: it is lost when the disk loses power or is unplugged. Put it in the connect script and in the start of every verification and copy script. Some USB bridges do not pass the command; check that the output shows the new value.
- **Verify:** `smartctl -l scterc` shows 70,70 right before every long job; the connect script fails if it does not.
- **Don't:** run a full verification of a suspect disk without ERC; leave ERC on while doing a last-chance restore.

### SEC-STOR-5: Large copies go one at a time, throttled, with stop conditions
- **Rule:** copy VMs to a backup disk sequentially, with a bandwidth limit, a pause between VMs, a free-space check before each, and automatic stop conditions.
- **Why:** parallel or full-speed copies saturate a shared HDD and starve the production VMs on it; an unattended job on a degrading disk writes terabytes into a failing device. Stopping early keeps the evidence and the data already written.
- **How:**
  - Limit rate on both ends (for example `--bwlimit <KiB/s>` in vzdump and a pipe limiter for slow NICs); use snapshot mode for running guests.
  - Check free space against the real used size plus a margin before each VM.
  - Re-run SEC-STOR-2 after each VM and stop if two consecutive re-reads fail, or if the sum of new pending and reallocated sectors exceeds a threshold you set beforehand (for example 50 new bad sectors in one run).
  - Make the script resumable (skip VMs that already have a finished backup; a partial file never counts) and do not edit a running shell script, since bash reads it as it executes.
  - Order by irreplaceability: the VMs whose data exists nowhere else go first.
- **Verify:** A dry-run mode prints the plan, order and space check without writing; a deliberate failure stops the batch.
- **Don't:** start all copies at once "to finish sooner"; keep copying after the first read failure.

### SEC-STOR-6: `fstrim` inside the guest before the backup
- **Rule:** run `fstrim` in each guest immediately before its backup, and make sure the virtual disk has `discard=on`.
- **Why:** deleted files whose blocks were never released still hold the old data. The backup copies them, and compression does not shrink them when the data was already compressed (video, archives). After a trim the freed blocks are zeros and the backup skips them. In practice a backup can copy tens of percent more than the live data until the guests are trimmed. If the guests already trim weekly with `fstrim.timer`, the file ends up near the real used size.
- **How:** the vzdump hook (`--script`, or the job's `script` option) is called as `<script> <phase> <mode> <vmid>`; on phase `backup-start` it trims the guest (SEC-STOR-7 for how). Check the effect by comparing the backup size with the used space inside the guest.
- **Rollback:** remove the hook from the job/command; nothing else changes.
- **Verify:** the log shows the trimmed amount per filesystem; backup size is near the used size.
- **Don't:** let a failed trim stop the backup: log it and continue; run the trim on a VM that is off or has no guest agent.

### SEC-STOR-7: Do the trim through the guest-agent socket, not through `qm agent`, inside a vzdump hook
- **Rule:** in a hook that runs during `backup-start`, talk to the guest agent's unix socket directly instead of `qm agent` or `qm guest`.
- **Why:** in that phase vzdump holds the VM's lock; `qm agent`/`qm guest` wait for that lock and hang, so the trim silently does not happen: the call hangs waiting for the lock.
- **How:** the socket is `/var/run/qemu-server/<vmid>.qga`. Send the sync handshake, then `guest-fstrim`, with long timeouts:
  ```python
  # python3 -I; argv[1] = socket path. Minimal client for guest-sync-delimited + guest-fstrim
  import json, socket, sys, random
  s = socket.socket(socket.AF_UNIX); s.settimeout(10); s.connect(sys.argv[1]); f = s.makefile('rwb')
  def cmd(c, a=None):
      f.write(json.dumps({"execute": c, **({"arguments": a} if a else {})}).encode() + b"\n"); f.flush()
      while True:
          l = f.readline().strip(b"\xff").strip()
          if l: return json.loads(l)
  n = random.randint(1, 2**31); f.write(b"\xff"); f.flush()
  r = cmd("guest-sync-delimited", {"id": n})
  while r.get("return") != n: r = json.loads(f.readline().strip(b"\xff").strip() or b"{}")
  s.settimeout(1800); print(cmd("guest-fstrim"))
  ```
  Wrap the call in `timeout`, skip with a log line if the socket does not exist (VM off or no agent) and always exit 0 so the backup proceeds.
- **Verify:** run the hook by hand against a running VM (`<hook> trim <vmid>`) and during a real backup; the log shows a trimmed total.
- **Don't:** call `qm agent <vmid> fstrim` from a `backup-start` hook.

### SEC-STOR-8: Never power on an old copy of a VM that has the same IP or MAC as the live one
- **Rule:** an older copy of a VM (on another host, on the backup disk, restored for a test) must never be started on the same network as the live VM while it carries the same IP and MAC.
- **Why:** duplicate addresses split traffic between two machines, corrupt ARP tables and, for stateful services (databases, queues, routers), diverge the data. The "harmless" old copy is the one that is eventually powered on in a hurry.
- **How:** keep such copies powered off and mark them (name, description, tag). To test a restore: restore to a new VM ID with unique identifiers (`qmrestore <file> <new-vmid> --unique 1`), disconnect its network (`qm set <new-vmid> --net0 <model>=<mac>,bridge=<bridge>,link_down=1`) or use an isolated bridge, and change the IP before any connection.
- **Verify:** the inventory of VMs lists each stale copy as "off, never start"; a restore test shows a different MAC than the live VM.
- **Don't:** start a stale copy "just to look" on the production bridge.

### SEC-STOR-9: Cold storage: monthly cycle, a last-OK marker on another disk, a 30-day alert
- **Rule:** an offline backup disk is connected on a schedule (monthly), refreshed and verified by scripts, and then disconnected. A marker file recording the last fully successful run lives on a different disk, and monitoring alerts when it is older than 30 days or missing.
- **Why:** an offline disk is protected from ransomware and from a compromised management plane, but nobody notices if the monthly ritual stops. The alert must not live on the disk that is unplugged.
- **How:** three scripted steps plus monitoring, each safe to re-run:
  1. `connect`: rescan the bus, check the disk identity, set SCT ERC (SEC-STOR-4), mount, enable the storages; leave the nightly job disabled while connected.
  2. `backup --verify`: vzdump of the critical VMs (snapshot, compression, notes hook, `keep-last=3` per VM), then verification (SEC-STOR-10). Only if the whole batch is OK, write the marker (date) onto the system disk, and save a SMART snapshot there too (SEC-STOR-3). Exit code distinct for "backup fine but an old file is unreadable".
  3. `store --confirm=<phrase>`: check the disk identity, that no vzdump or process uses the mount, then disable the job and the storages, `sync`, unmount, remove the disk from the kernel; on failure before releasing the disk, restore the previous state. Then power down or unplug.
  4. Monitoring: item = age of the marker in days; Warning above 30, and one for "marker missing".
  Before unplugging, list which monitoring triggers fire when the disk disappears (mount space, SMART, storage status of the hypervisor templates) and handle them first; the disappearance of a disk should not page.
- **Verify:** the marker date moves after each cycle; set the marker 31 days back on a test and confirm the alert reaches a person (SEC-DET-11).
- **Don't:** keep the marker on the cold disk; write the marker when the verification failed; leave the disk connected "until next time".

### SEC-STOR-10: Verify old backups on a rotation
- **Rule:** each backup cycle fully verifies what is new and a rotating slice of what is old, with progress kept on a different disk, so that every file is re-read within a known number of cycles.
- **Why:** a backup that is read only on the day it is written says nothing about next year. Verifying everything every time takes days on a big HDD; a slice per run (about one sixth, so everything is re-read in about six cycles) keeps the cost bounded.
- **How:** new files: `zstd -t` for compressed dumps and the SHA-256 comparison (SEC-STOR-1). Old files: a share of the stored sums (`sha256sum -c`), with the state file (path, last checked, result) on the system disk. Failures are listed; known and accepted failures go into an ignore list, one path per line, so they do not hide new ones. Run with SCT ERC on (SEC-STOR-4) and as a background unit.
- **Verify:** the state file shows every file with a last-checked date no older than the cycle count allows; a deliberately corrupted test file is found within one full rotation.
- **Don't:** keep an unreadable backup "for now" without recording it as lost; verify only the newest.

### SEC-STOR-11: Virtual disk cache: `none` by default, and never `writethrough` on btrfs
- **Rule:** use `cache=none` for VM disks unless an A/B measurement on your own workload shows another mode is better. Never use `cache=writethrough` for disks stored on btrfs.
- **Why:** `writethrough` makes each guest write synchronous (O_DSYNC). On btrfs that forces a log-tree commit, with duplicated metadata, per write. Measured effect with a dozen VMs on one btrfs HDD: average write latency seen by the guests went from tens of milliseconds to several seconds (2,900-5,300 ms); the host did about 350 writes/s against 24 on a comparable xfs host; host iowait doubled, and the other VMs on the same disk suffered. The read side gained almost nothing, because the VMs asked for little.
- **How:**
  - Measure before and after, over at least 24 hours and in the same hours of the day (demand varies by time): per-VM write/read latency from the hypervisor's `info blockstats` (`qm monitor <vmid>`; average = total time / operations since boot), bytes read from the physical disk per byte the VM asked for, and host iowait and disk utilization.
  - Change the mode with the full drive string: `qm set <vmid> --scsi0 <storage>:<volume>,cache=none` plus an orderly reboot of the VM. Keep a change log per host (date, old value, new value, how to revert).
  - Compare on a subset first (A/B), never the whole fleet at once.
- **Rollback:** `qm set <vmid> --scsi0 <storage>:<volume>,cache=<previous>` and an orderly reboot.
- **Verify:** write latency per VM is back to the baseline range; host iowait fell.
- **Don't:** assume host-side caching helps because the host has free RAM; compare metrics from different hours; run a cache experiment while a large backup is reading the same disks (the numbers are unusable).

### SEC-STOR-12: `writeback` buys little and risks data in a power cut
- **Rule:** keep `cache=writeback` only for disks whose data can be rebuilt, on hosts with power protection, and only if a measurement shows a real gain.
- **Why:** with `writeback` writes sit in host RAM until the guest asks for a flush; a power cut or host hang loses them and can leave the guest filesystem inconsistent. In a 24-hour A/B it read only about 7 % less from the disk per unit served and 1.4 ms faster on reads, while write latency was almost double (about 43 ms against 24 ms).
- **How:** decide with the measurements of SEC-STOR-11; where the data is rebuildable (a data set that can be re-verified and re-downloaded) the cost of a loss is a long recheck per VM, not zero.
- **Verify:** the list of VMs in `writeback` is explicit, each with a reason, and none holds unique data.
- **Don't:** use it on databases, mail, or anything you cannot regenerate.

### SEC-STOR-13: A large host `read_ahead_kb` amplifies reads on busy HDDs; persist the fix by disk identity
- **Rule:** when the host reads much more from the HDD than the VMs request, check `read_ahead_kb` of the physical device and lower it (256 KB is a reasonable start for random-read workloads), then persist it with a udev rule that matches the disk, not its kernel name.
- **Why:** with the host page cache in the path, a readahead of 8 MB drags in data nobody asked for: in one measurement a VM's disk read 446 MB from the HDD for 36 MB requested (6x amplification across the VMs). At 256 KB the amplification of the same VMs fell to 1.7x. The value lives only in `/sys` and returns to its default at the next reboot, which would contaminate any experiment and silently undo the fix.
- **How:**
  ```bash
  cat /sys/block/<dev>/queue/read_ahead_kb
  echo 256 > /sys/block/<dev>/queue/read_ahead_kb                       # immediate, volatile
  # persistent, matched by serial (find it with: udevadm info -q property -n /dev/<dev> | grep ID_SERIAL_SHORT)
  # /etc/udev/rules.d/61-readahead-<label>.rules
  ACTION=="add|change", SUBSYSTEM=="block", ENV{ID_SERIAL_SHORT}=="<serial>", ATTR{queue/read_ahead_kb}="256"
  udevadm control --reload && udevadm trigger --subsystem-match=block --action=change
  ```
  Log the change (date, previous value, new value, how to revert). Measure amplification as bytes read from the disk divided by bytes requested by the VMs; on a host where VM disks use `cache=none` on xfs it was already 1.0x with 8 MB, so do not copy the number: measure first.
- **Rollback:** write the previous value back and remove the rule file.
- **Verify:** `cat` of the file after a reboot (or a `trigger`) shows 256; amplification measured again.
- **Don't:** match the rule on `KERNEL=="sdb"`: the letter moves when disks are added; tune readahead without measuring the amplification first.

### SEC-STOR-14: Periodic disk clicks: count head load cycles before assuming a failing head
- **Rule:** when an HDD clicks periodically, read SMART `Load_Cycle_Count` (193) and `Power-Off_Retract_Count` (192) twice, some minutes apart, under the same load, before deciding anything.
- **Why:** if the counter rises in step with the clicks, the sound is the head parking and unparking, which is normal mechanics (drives are rated for hundreds of thousands of cycles), not a head striking the platter. On a degraded drive with APM already at 254 the counter rose 4 in about 6 minutes, matching the clicks. What remains is either extended power-control timers (EPC) parking the head between write bursts, or the drive retracting while it recovers hard reads.
- **How:**
  ```bash
  smartctl -A /dev/disk/by-id/<disk> | grep -E 'Load_Cycle|Retract|Seek_Error'   # twice, N minutes apart
  hdparm -B /dev/disk/by-id/<disk>                                              # APM; 254/255 = no APM parking
  # to tell EPC from recovery: record, then disable EPC and count again (openSeaChest; note whether the change persists)
  openSeaChest_PowerControl -d <dev> --showEPCSettings
  openSeaChest_PowerControl -d <dev> --EPCfeature disable
  ```
- **Rollback:** re-enable EPC (`--EPCfeature enable`) or restore the recorded settings.
- **Verify:** counter rate before and after, logged with the load at the time.
- **Don't:** change power settings in the middle of a measurement that depends on that disk; assume clicks mean imminent failure (or that they don't) without the counter.

## Checklist: copying to a backup disk

1) Disk identified by `/dev/disk/by-id`, SMART snapshot saved, SCT ERC set (SEC-STOR-3, SEC-STOR-4).
2) Copy one VM at a time, throttled, stop conditions in place; most irreplaceable first (SEC-STOR-5).
3) `fstrim` hook active through the guest-agent socket (SEC-STOR-6, SEC-STOR-7).
4) Stream hash at source and file hash from the destination, full re-read, result logged (SEC-STOR-1, SEC-STOR-2).
5) Stale VM copies marked "never start" (SEC-STOR-8).
6) Offline disk: monthly cycle, marker on another disk, 30-day alert tested (SEC-STOR-9).
7) Rotating verification with a state file on another disk (SEC-STOR-10).
8) VM disk cache and readahead changed only with measurements and a change log (SEC-STOR-11 to SEC-STOR-13).
9) Unusual noise investigated with SMART counters, not by ear (SEC-STOR-14).
