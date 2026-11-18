---
title: Serving much content from HDDs with little wear and heat (seeding, IO limits, thermal throttle, caches, btrfs vs xfs)
scope: Proxmox VE hypervisors with spinning disks, VMs that seed or serve large static content (BitTorrent clients such as qBittorrent/libtorrent), virtual-disk IO limits, disk temperature and SSD wear, btrfs and xfs VM stores
when_to_use: disks run hot or the hot season is coming; a host with many seeding VMs has high iowait; deciding whether a read cache (RAM or SSD) is worth it; choosing btrfs or xfs for VM images; tuning a torrent client for HDDs; planning a thermal or time-of-day throttle; designing an experiment before changing storage settings
related: [README.md, backups-and-storage.md, detection-and-audit.md, patching.md, policies.md]
---
# Serving much content from HDDs with little wear and heat

Most of what hurts a disk farm is not what it seems. Before tuning anything, find out which of two different problems you have (seek-bound reads, or write amplification from the file system under the VM images), whether the heat comes from the load at all, and what each change really buys. This doc holds the reusable practice; the cache-mode and readahead rules it builds on are in [backups-and-storage.md](backups-and-storage.md) (SEC-STOR-11 to SEC-STOR-13) and are referenced, not repeated.

## Evidence labels (read this first)
Every claim about effect carries one label. Never upgrade a label without a new measurement.

| Label | Meaning |
|---|---|
| **measured** | observed on a real deployment with a baseline and a comparison |
| **documented** | stated in the vendor or project documentation (the rule names the source kind) |
| **expected** | reasoning or reports from other users; plausible, not verified here |
| **measure first** | no number exists; run the experiment of SEC-PERF-3 before rolling out |

The rules marked **expected** or **measure first** are plans, not verified results. Update the label and the number when your own A/B finishes.

## Quick decision table

| Situation | Do | Rule |
|---|---|---|
| Disks are hot and you want to "throttle the seeds" | Measure temperature against disk busy % first; airflow is the proven lever | SEC-PERF-1 |
| A copy, scan or backup reads the disk for days | Run it in the coolest hours, with a MB/s cap and idle IO class | SEC-PERF-2 |
| About to change any setting on many VMs | One variable, paired control, same hours, change log | SEC-PERF-3 |
| High iowait: is it reads or writes? | Diagnose by amplification and write MB/s before choosing a remedy | SEC-PERF-4 |
| Many peers served at once from a HDD | Cap unchoke slots before capping bandwidth | SEC-PERF-5 |
| Torrent client with many IO threads on a 1-core guest | Fewer threads; confirm whether a restart is needed | SEC-PERF-6 |
| Client restarted and rechecks everything at once | One hash check at a time | SEC-PERF-7 |
| One VM can saturate the shared disk | Per-virtual-disk read limits as a hard backstop | SEC-PERF-8 |
| Disk passes a temperature threshold | Host-side thermal throttle, dry-run first, with a kill switch | SEC-PERF-9 |
| Wish to cap upload during the hottest hours | Only after at least a week of data; one control point | SEC-PERF-10 |
| Considering an SSD or RAM read cache | Compute the coverage curve; flat demand means no | SEC-PERF-11 |
| Considering more guest RAM "for cache" | Only for OOM, never for cache, when the working set is far larger | SEC-PERF-12 |
| btrfs host writes far more than its guests ask | Treat it as write amplification; follow the ladder | SEC-PERF-13, SEC-PERF-14 |
| Database in a guest on a shared HDD | Relax the commit flush only if losing a second is acceptable | SEC-PERF-15 |
| Service VMs suffer on a disk shared with seeders | IO scheduler with weights; test once, do not persist blindly | SEC-PERF-16 |
| Tuning readahead | Know which layer (host, guest) acts for your cache mode | SEC-PERF-17 |
| Trying a different libtorrent disk backend | One instance, no partial files, restart expected | SEC-PERF-18 |
| Tempted to reformat or move storage in summer | Don't; verify the backup first | SEC-PERF-19 |
| Restarting guests for a setting | Rolling, one at a time, stop at the first non-OK | SEC-PERF-20 |
| Config files of guests that live on another host | Remove or mark them | SEC-PERF-21 |

## Rules

### SEC-PERF-1: Heat follows the room, not the seed load; airflow first, and measure before throttling
- **Rule:** before limiting upload to cool a disk, correlate its temperature with its utilisation and with the same metric on other hosts in the same room. If the temperature follows the room, fix airflow first. Take the drive's rated operating temperature from its datasheet; SMART does not report it.
- **Why:** **measured:** in one comparison, two hosts with very different upload load (one served about eleven times more than the other) had daily-mean disk temperatures that correlated at r = 0.99 across 28 days, while temperature against the busy percentage of the disk on the busy host was r = -0.02. Both drifted up about 0.26 degrees C per day as the season changed (roughly +10 degrees C in a month). **measured:** a 120 mm fan about 25 cm above a disk under sustained sequential reads dropped it from 50 to 40 degrees C; it is the only documented ten-degree gain. **expected:** all software tuning together buys perhaps 1 to 3 degrees C; it reduces wear and latency, it does not replace air.
- **How:**
  - Take the daily mean and the hourly profile of temperature per host (SMART attribute 194 via `smartctl -A /dev/disk/by-id/<disk-id>`, or the monitoring item) and the busy percentage of the disk; compute the correlations (a spreadsheet or `python3 -I` is enough).
  - Physical first: fan on the drive cage, dust out of filters and case, a free exit for hot air, equipment away from windows and sun. Opening a case means powering the host off: plan it as a host reboot.
  - Alert on temperature only for mechanical disks and on wear for SSDs; use separate thresholds (for example a warning at 45 and a high at 50 degrees C for HDDs, an information level at 50 percent wear for SSDs, then 80 and 90). Confirm those numbers against the datasheet before fixing them.
  - Compare the lifetime maximum from `smartctl -l scttempsts` with the datasheet limit; a drive that already saw a maximum close to its limit has no margin.
- **Verify:** hourly mean temperature in the hottest hours, three days before and three days after the physical change; correlations recomputed after a season.
- **Don't:** assume that fewer uploads means a cooler disk; set thresholds without the datasheet; extrapolate one day of load as seasonality.

### SEC-PERF-2: Bulk sequential reads go in the coolest hours, with a MB/s cap and idle IO class
- **Rule:** backups of VMs, parity or verification jobs, scans and any large copy that reads the HDDs run in the coolest hours (late night to early morning local time in summer), with a bandwidth cap and the idle IO class.
- **Why:** **measured:** a multi-day copy of several terabytes read one host's disk at about 31 MB/s with a read wait of about 33 ms, the largest sustained read on that host, and seeders on the same disk competed with it. **measured:** disks ran 2 to 3 degrees C hotter between mid-morning and late afternoon than at night. **expected:** a lower cap lengthens the job but lowers drive temperature; not measured yet.
- **How:** `ionice -c3 nice -n 19 <command>`; a rate limiter in the read pipe (a small `throttle` script or `pv -L <rate>`), or `--bwlimit <KiB/s>` in vzdump; schedule by `systemd` timers or cron within the cool window; keep the order and the stop conditions of SEC-STOR-5. Do not change a job already running without the owner's decision: a longer copy keeps guests in snapshot longer.
- **Verify:** disk temperature during the job at two different caps, and the upload of the guests in the same hour.
- **Don't:** start a bulk read in the hottest hours "because the disk is idle"; decide a cap without checking how long the job then takes.

### SEC-PERF-3: One variable at a time, against a paired control, in the same hours of the audience
- **Rule:** change one setting on a test VM, keep a control VM with similar load untouched, compare over the same window of at least 24 hours (48 for reads), and record every change with its revert command.
- **Why:** demand depends strongly on the hour in the audience's timezone and on the VM; comparing with yesterday or with a different VM says nothing. Two jobs that move the load (a large copy, a VM migration onto the host) make a baseline useless: wait for them to end. On a host with very low demand a read test has no statistical signal; run read tests where demand is real and write tests where writes are the problem.
- **How:**
  - Baseline: 24 to 48 hours of the collector with no change, after any big copy or migration finished.
  - Primary metric: megabytes read from the physical disk per megabyte uploaded (lower is better). Secondary: virtual disk read and write latency per VM, host iowait, disk busy percentage, disk temperature.
  - Pairs: VMs with nearly equal upload over a recent day. The two or three largest VMs are on another scale; do not use them as test or control without an explicit decision.
  - Success criterion, stated before the test: the primary metric or latency falls at equal upload, upload does not drop by more than 10 percent, and write latency stays below about 100 ms.
  - Change log on each host (date and time, old value, new value, how to revert), the same format as in SEC-STOR-11.
- **Rollback:** the revert command of each log line.
- **Verify:** the analysis groups intervals by configuration and shows control and test side by side over the same hours.
- **Don't:** change several settings in one step; compare windows with different weekdays or hours; run an experiment while a large copy reads the same disks.

### SEC-PERF-4: Diagnose which problem you have before choosing a remedy
- **Rule:** classify each host as read-bound (seeks), write-bound (file-system write amplification), or neither, with three numbers: read amplification, disk busy percentage with its distribution, and write MB/s at the disk against write MB/s requested by the guests.
- **Why:** the remedies are different and the wrong one does nothing. **measured:** on an xfs host the disk was not saturated (median busy about 23 percent, 95th percentile about 64 percent, read amplification 1.00x, writes about 0.4 MB/s) while serving hundreds of gigabytes a day: attack seeks, peaks and bulk reads. On a btrfs host with about one eleventh of the upload, the disk received about 6.5 MB/s of writes (roughly 350 writes per second) while the guests asked for about 1 MB/s, around 86 percent of it btrfs metadata, with iowait a median of 13 percent: attack the origin of the writes and the structure. A cap on upload on the second host moves almost nothing.
- **How:** per-guest requested bytes from the hypervisor (disk read/write counters or `info blockstats`), physical bytes from the process IO counters of the VM process (`/proc/<pid>/io`) and from `iostat -x`; amplification = physical read bytes / requested bytes. Read the 95th percentile, not the mean.
- **Verify:** a table per host with the three numbers and the chosen remedy; the table is redone after each change.
- **Don't:** apply the read remedies (slots, threads) to a write-bound host or the write remedies (mount options, nodatacow) to a read-bound one.

### SEC-PERF-5: Cap unchoke slots before throughput
- **Rule:** limit the number of simultaneously unchoked peers (qBittorrent: global upload slots and slots per torrent) to a moderate value, for example 25 global and 4 per torrent, and keep the "fastest upload" choking algorithm and fixed slot behaviour.
- **Why:** each unchoked peer is a separate read stream; on a HDD many streams mean more seeks, so fewer streams per torrent should mean more sequential reading per stream. **documented** (libtorrent reference): the slot is the number of unchoked peers, and the documentation only discusses raising it for maximum speed. **expected:** fewer seeks and no throughput loss; reports from HDD users suggest values around 5 slots. **measured (in favour of a moderate cap):** the instance running with 20 global and 4 per torrent served the largest share of the host's upload with read amplification 1.00x, so that limit did not strangle it. **measure first:** no number from a real deployment for the benefit in megabytes read per megabyte uploaded.
- **How:** API `app/setPreferences` with `json={"max_uploads":25,"max_uploads_per_torrent":4}` (use the keys your client version documents); applied without restart and persisted by the client. Test on the paired VMs of SEC-PERF-3 for 48 hours, then roll out to the fleet a few VMs a day. Remove "unlimited" (-1) values left on instances that have no connection cap either.
- **Rollback:** set both keys to -1 through the same API (immediate).
- **Verify:** megabytes read per megabyte uploaded and read latency, test against control; upload within 10 percent of control.
- **Don't:** roll out fleet-wide without the A/B; lower the per-torrent value for a single very requested torrent without checking peer speed.

### SEC-PERF-6: Fewer asynchronous IO threads on single-core guests
- **Rule:** on guests with one core, lower the client's asynchronous IO threads (default 10 in qBittorrent) to about 4; leave multi-core guests as they are; keep hashing threads at 1.
- **Why:** **expected:** with up to ten reads in flight per VM and twenty VMs, a HDD only queues them and read latency grows (a read wait of tens of milliseconds was seen during a heavy copy). With memory-mapped IO the real reads are page faults of the process, so the setting may change nothing. **measure first:** no number from a real deployment.
- **How:** API key `async_io_threads` (UI: Advanced, asynchronous IO threads). Some client versions flag it as "restart required": check in the UI of one guest. If it does, it waits for the next rolling restart (SEC-PERF-20), not before. Test on one pair (SEC-PERF-3).
- **Rollback:** set the previous value (and restart if required).
- **Verify:** read latency per VM, test against control.
- **Don't:** restart a client just for this; raise threads to "go faster" on a HDD.

### SEC-PERF-7: Limit concurrent hash checks so that a restart does not become a read storm
- **Rule:** set the client's maximum of simultaneous checking torrents to 1 on every instance (qBittorrent key `max_active_checking_torrents`).
- **Why:** after a power cut or an unclean stop the client rechecks everything it finds without a clean-close marker; with many torrents per VM and many VMs per disk all checking at once flatten the disk. **measured:** instances of one fleet were found with the value at 1 on some and at -1 (unlimited) on others, so set it uniformly. **measure first:** some versions ignore the saved `max_active_*` values when queueing is disabled; verify that this one is applied.
- **How:** set it through the API (no restart). At the next orderly restart of one instance, count torrents in the checking states (`torrents/info?filter=checking`, read-only) to see whether the limit applies.
- **Rollback:** set it back to -1.
- **Verify:** at most one torrent in a checking state after a restart.
- **Don't:** assume it works because the field accepted the value.

### SEC-PERF-8: Per-virtual-disk read limits as a hard backstop
- **Rule:** if a single VM can saturate the shared disk, put an upper bound on its disk reads (Proxmox `mbps_rd`, `mbps_rd_max`, `iops_rd`, `iops_rd_max`; the write equivalents exist too) and treat it as a ceiling for the worst case, not as a cooling tool.
- **Why:** **measured:** one seeding VM peaked at 16 MB/s of reads. **documented** (Proxmox VM configuration reference): the four read limits exist per drive. **expected:** a limit of about 8 to 10 MB/s with burst bounds the worst case without touching the service VMs on the disk. It limits MB/s, not seeks, so slots (SEC-PERF-5) remain the lever for seeks. It also throttles rechecks and copies inside the guest, and a queued read raises the latency the guest sees. The sum of many limited VMs can still saturate the disk.
- **How:** `qm set <vmid> --scsi0 <storage>:<volume>,<all current options>,mbps_rd=<N>,mbps_rd_max=<burst>`. `qm set` replaces the whole drive line, so first copy every current option (cache mode, discard, iothread, ssd flag) from `qm config <vmid>` and add the new ones. **measure first:** whether the limit applies live on a running VM in your version; if the config shows it as pending it waits for the next rolling restart.
- **Rollback:** the same command with `mbps_rd=0`, or the original line.
- **Verify:** read latency, upload and disk MB/s for 48 hours on one test VM; the drive line still shows every original option.
- **Don't:** put the limit on all VMs at once; write the `qm set` line from memory.

### SEC-PERF-9: Thermal throttle from the host: dry-run first, fail-static, kill switch, never depend on the monitoring VM
- **Rule:** if a thermal throttle is built, run it on each hypervisor (not on a workstation or in the monitoring system), read the disk temperature itself, act on guests through the client's API, start in dry-run for two weeks, keep a state file, and make failure leave the current state unchanged.
- **Why:** the monitoring system can be down (for example during a migration), and a single point of failure here would remove the safety net exactly when it is needed. **expected:** it bounds the heat the seeds can add once a disk is past its threshold; **measure first** whether it lowers temperature at all, given SEC-PERF-1 (r = -0.02). The dry-run answers that: if the simulated throttle would have acted and the temperature rose anyway, it is not justified.
- **How (design, not validated in production):**
  - Input: `smartctl -A -d sat -n standby /dev/disk/by-id/<disk-id>`, attribute 194, raw value masked to the low byte. `smartctl` returns a bit mask in its exit code even after a good read: discard a reading only when there is no attribute 194. Filter with the median of the last 5 readings (5 minutes).
  - States with hysteresis: normal; level 1 when the median is at or above 45 degrees C for 5 minutes (leaves below 42 for 10 minutes); level 2 when at or above 50 for 3 minutes (leaves below 47 for 10 minutes). Per-VM cap at level 1 about 60 percent of that VM's recent 95th percentile of upload, at level 2 about 30 percent, with a floor (for example 200 KiB/s) so the instance stays present in the swarm. The percentages are starting points; the dry-run sets them. With fewer than 7 days of data mark the log rows "provisional".
  - Actuation: the client's API calls `transfer/setUploadLimit` (bytes per second, 0 = unlimited) and `transfer/uploadLimit` to read it back. Prefer them to the `up_limit` preference, whose unit is easy to get wrong by a factor of 1024.
  - Persistence: the limit stays in the client after the script dies. Keep a state file (level, entry time, original value per VM); at start, reconcile the real limit of every VM with the expected one.
  - Login: one session per VM, cookie reused; a client bans an address after a few failed logins (5 in an hour by default): never retry authentication in a loop, log and skip that VM.
  - Safety: dry-run by default; an off switch (a file whose presence restores every limit and exits); subcommands for status, restore, dry-run, apply; fail-static (no reading means no change, a log mark after 10 consecutive failures; never lower a limit for lack of data); a monitoring item for the current level and a trigger if a level lasts more than 6 hours, so a forgotten throttle does not stay for weeks.
  - Do not start the apply mode while a large copy (SEC-PERF-2) is the main heat source: slowing the seeds then hides the cause.
  - Reuse the existing host modules and credentials; never copy secrets into the new script.
- **Rollback:** the off switch restores every limit; removing the timer ends it.
- **Verify:** in dry-run, the log answers: how many hours a day it would be at each level, and whether temperature fell within 30 minutes of each simulated cap.
- **Don't:** use the client's built-in scheduler for this (SEC-PERF-10); depend on the monitoring system for the temperature input; ship it in apply mode first.

### SEC-PERF-10: A time-of-day upload cap is one control point, set only with a week of data
- **Rule:** if upload is capped in the hottest hours, implement it in the same script as the thermal throttle (effective cap = the smaller of the two), and fix the numbers only after at least 7 days of collector data that include a weekend.
- **Why:** the client's scheduler uses the alternative-speed limit, which replaces the normal limit while active and would fight the thermal throttle; its schedule also follows each guest's local time zone, while the host has a single clock. **measured:** upload peaked at about 22 to 24 GB per hour in four evening hours of the audience against about 7.5 GB per hour in the early morning, and the peak coincided with the hottest hour, from one sample day. **expected:** capping the peak at about 16 GB per hour would trim about 7 percent of the day's upload, part deferred and part lost to other seeders; the cost is real availability for content whose value is being available.
- **How:** apply through `transfer/setUploadLimit` with the state file of SEC-PERF-9; make sure no instance has the alternative limit enabled at the same time.
- **Rollback:** restore command or `0` through the API.
- **Verify:** upload per hour and temperature in the capped hours, with and without the cap.
- **Don't:** fix the cap from one day of data; enable the client scheduler together with a script.

### SEC-PERF-11: Read caches (SSD or RAM) only when demand is skewed; compute the coverage curve first
- **Rule:** before adding an SSD or RAM read cache, compute from the upload logs how much of the uploaded bytes the hottest X percent of content would cover. Do not build the cache unless that curve is steep.
- **Why:** **measured:** the demand was almost flat. Cumulative upload coverage by the most requested content: top 1 percent of the archive about 9 percent of the uploads, top 5 percent about 25, top 10 percent about 39 (the theoretical ceiling with perfect placement), 50 percent of the archive for half the uploads, about 80 to 90 percent of the archive for 80 to 90 percent. Each active gigabyte was served only about 0.6 times a day (351 GB served over 555 GB touched in 24 hours). **measured:** a host read cache of 12 to 16 GB gave only 7 percent less disk read per megabyte uploaded. An SSD cache of 120 to 240 GB would cover about 9 percent.
- **How:** per-torrent or per-file upload totals over days, sorted descending, cumulative sum against cumulative size. Check SSD wear (`smartctl -A`, the wear attribute) before assigning any role to an SSD: a drive already at half its life should not take cache writes. If it is ever reopened: after the other measures a disk still shows a sustained 95th-percentile busy above 80 percent or temperatures at or above the threshold, **and** at least 1 TB of new SSD is available, in a write-through cache mode (bcache `writethrough` or a dm-cache without delayed writes; in write-back an SSD failure loses data). Expect at most about 25 percent coverage.
- **Verify:** the coverage table exists for your own data before any purchase.
- **Don't:** copy these percentages; they belong to one data set. Do not cache on an SSD that is already worn.

### SEC-PERF-12: More guest RAM is for avoiding OOM, not for caching
- **Rule:** raise a guest's memory only when it shows out-of-memory events; do not add RAM "for cache" when the touched set is far larger than the cache you could add. Keep guests without swap.
- **Why:** **measured:** the set of data touched in 24 hours was 555 GB and in 7 days 2.9 TB, so 0.5 to 1 GB of page cache per guest is 0.1 to 0.2 percent of a guest's disk, and the host cache of 12 to 16 GB had already given only 7 percent (SEC-PERF-11). The hypervisor itself was using most of its swap: more RAM to guests makes the host worse. **measured:** a guest was killed by OOM at 1000 MB and fixed at 1500 MB.
- **How:** raise memory with `qm set <vmid> --memory <MB>`; it needs a VM restart (not hot), so it goes into a rolling restart (SEC-PERF-20). Leave about 60 to 70 percent of a guest's RAM to the page cache; the client's own "working set limit" does not bound the page cache with memory-mapped IO on Linux (cosmetic).
- **Verify:** no OOM in the guest's log for a week after the change.
- **Don't:** add swap to guests; resize several at once.

### SEC-PERF-13: btrfs under VM images amplifies guest flushes into metadata writes; xfs does not
- **Rule:** for a VM store whose main load is "many guests that rarely write", prefer xfs. If the store is btrfs, expect heavy metadata writes and follow the ladder of SEC-PERF-14 before touching mount options.
- **Why:** **measured:** on a btrfs store with compression (zstd level 3) and duplicated metadata, the disk received about 4 to 6.5 MB/s of writes (around 350 per second) while the guests asked for about 0.7 to 1 MB/s: roughly 6x amplification, about 86 percent metadata, from copy-on-write, DUP metadata, 30-second commits and many small writes plus flushes; each guest flush (one per ext4 journal commit) cost about 1.5 s on it. The comparable xfs host wrote about 0.17 to 0.4 MB/s while serving about eleven times more. **measured:** a single 830 GB image had 424,424 extents. Compression of video is useless (almost no saving, real CPU cost on an old processor). Do not use `cache=writethrough` on btrfs (SEC-STOR-11); `autodefrag` is bad for large VM images; turning metadata DUP to single trades away redundancy.
- **How:** decide the file system when the store is built. For an existing btrfs store use SEC-PERF-14; the move to xfs is SEC-PERF-19.
- **Verify:** the write-bound check of SEC-PERF-4 (disk write MB/s against guest-requested MB/s).
- **Don't:** compare with `none` vs `writeback` and conclude from one VM; reformat in a hurry.

### SEC-PERF-14: On btrfs, reduce guest writes first, then mount options, then nodatacow, then migration
- **Rule:** reduce the guests' own write rate (mount options in the guest, long resume-data interval, quiet logs), then database flushes (SEC-PERF-15), then the host's mount options, then `nodatacow` on one test VM, and only then consider moving to xfs.
- **Why and expected effect, in order:**
  1. **Inside each guest, `noatime` and a longer ext4 `commit=` (for example 60 s instead of 5 s):** **expected:** `noatime` alone is negligible with `relatime` (at most one access-time update per file per day: tens of MB a day in total); the longer commit cuts the number of flushes sent to the btrfs host, and flushes are the expensive part. **measure first.** Cost: after a power cut up to about 60 s of unconfirmed metadata is lost instead of about 5 s, and ext4 stays consistent. No restart: `mount -o remount,noatime,commit=60 /` plus the fstab line.
  2. **Longer `save_resume_data_interval` (for example 360 min instead of 60):** **expected:** negligible on xfs; on btrfs each rewritten file is a flush with metadata copy-on-write, so low but not zero; verify whether files are rewritten even when nothing changed (`find <dir> -name '*.fastresume' -mmin -60 | wc -l` against the total). Cost: a power cut loses up to that many hours of transfer statistics, not the state of complete torrents.
  3. **Host mount `commit=120`:** **expected: low.** A guest flush is resolved through the log tree, not a full commit, so most of the metadata writes do not come from the 30-second interval. It matters more once the guests are quiet. Cost: up to 120 s of unsynced writes lost in a power cut, more dirty RAM. Test it for 24 hours; the revert is `mount -o remount,commit=30 <mountpoint>`.
  4. **`nodatacow` for the images of one test VM (guest off):** **documented** (btrfs docs): it implies no data checksums and no compression and applies only to new files. Procedure: power the VM off, create a new directory with `chattr +C`, copy the image into it with `cp --reflink=never` (not `mv`), point the disk at the copy, start and verify; keep the old image until validated. **expected:** the largest possible reduction of the host's write rate, because overwrites happen in place. Cost: no scrub-detected corruption in that image (the guest file system has none either), partial writes possible in a power cut (the guest journal tolerates them), hundreds of gigabytes of copy time and free space needed, and no sharing of extents with snapshots. Do it at night with a rate cap (SEC-PERF-2).
  5. **Move to xfs:** SEC-PERF-19.
  Measure each step on the host's disk write MB/s and writes per second and on the guest's write latency and flush rate (SEC-PERF-3). If step 4 brings the write rate below about 2 MB/s, do not migrate.
- **Verify:** write MB/s and writes per second at the disk before and after each step; guest write latency stays below about 100 ms.
- **Don't:** jump to step 4 or 5 without having measured steps 1 and 2; run nodatacow while a backup of those images is reading them.

### SEC-PERF-15: Relax a database's commit flush on a shared HDD only if losing one second is acceptable
- **Rule:** for a database in a guest on a shared HDD, find out whether it is the biggest source of flushes; if it is and a crash may lose the last second of commits, set the InnoDB flush mode to 2 and give the buffer pool and log a size that fits the data.
- **Why:** **measured:** a monitoring database was the guest that requested the most flushes. Setting `innodb_flush_log_at_trx_commit=2`, a larger buffer pool (128 to 768 MB) and a 256 MB log cut its fsync rate from 8.4/s to 0.96/s (-89 percent) and the host disk's write rate from 4.77 to 4.20 MB/s (-12 percent, a two-minute sample, so treat the 12 percent as indicative). The remainder was btrfs amplification of the other guests.
- **How:** a drop-in file in the database's configuration directory (no edit of the main file); restart the database service; keep the previous state so you can remove the file. Confirm with the guest's own counters.
- **Rollback:** delete the drop-in file and restart the database service.
- **Verify:** fsync per second in the database, writes at the disk.
- **Don't:** apply it to a database whose last second matters (payments, queues, mail); judge by a two-minute sample alone.

### SEC-PERF-16: IO scheduler and weights protect service VMs on a shared disk; they do not cool it
- **Rule:** if routers, monitoring or web VMs share a HDD with seeders and suffer latency, test a scheduler that honours weights (BFQ or `io.cost`) with low weights on the seeders and high on the service VMs. Run one short test; do not persist before deciding.
- **Why:** **documented** (kernel docs): the cgroup `io.weight` is honoured only by BFQ (as `io.bfq.weight`, 1 to 1000) or `io.cost`; with `mq-deadline` it does nothing. **documented:** BFQ has more per-request overhead than `mq-deadline` (about 1.9 microseconds against 0.7). **expected:** it protects latency; it does not lower temperature; with many random streams on a HDD BFQ may lose throughput to idling.
- **How:** `echo bfq > /sys/block/<dev>/queue/scheduler`, `echo 0 > /sys/block/<dev>/queue/iosched/slice_idle`, `systemctl set-property <vm-unit> IOWeight=<n>` per VM scope. Measure latency of the service VMs and total throughput for 24 hours in peak hours.
- **Rollback:** `echo mq-deadline > /sys/block/<dev>/queue/scheduler` (instant). No udev rule until the decision is taken.
- **Verify:** service-VM latency falls without the disk's total throughput falling more than the test allows.
- **Don't:** use it on a host with no service VMs; test it on a router's disk without a window and a rollback plan.

### SEC-PERF-17: Know which layer's readahead acts for your cache mode
- **Rule:** before tuning readahead, check the cache mode of the drives: with `cache=none` (direct IO) the host's readahead does not act on the images, so only the guest's readahead matters; with a host-cached mode the host's value matters.
- **Why:** host rules are in SEC-STOR-13. **measured:** the guests' readahead was 128 KB everywhere; the xfs host showed read amplification 1.00x with it, the btrfs host 1.7x after the host fix. The remaining excess probably comes from btrfs reading whole compressed extents (up to 128 KiB) to deliver a small piece and from the guests that had been in a host-cached mode: **expected**, not measured. Lowering the guest value (for example to 64 KB) is **expected** to give a small gain. A large host value is still useful for sequential copies of the images, so leave it where copies run.
- **How:** in the guest `echo 64 > /sys/block/<dev>/queue/read_ahead_kb` with a udev rule; compare amplification of one guest against a control, only while the cache mode is `none` (SEC-PERF-3). Check after every reboot of a host that the udev rule from SEC-STOR-13 is in place; otherwise the value returns to its default.
- **Rollback:** write the previous value.
- **Verify:** amplification of the test VM against the control.
- **Don't:** test the guest value while some VMs are in a host-cached mode.

### SEC-PERF-18: A different libtorrent disk backend: test on one instance without partial files
- **Rule:** to try the POSIX disk backend instead of memory mapping, test it on one instance per host and only on one without partially downloaded torrents.
- **Why:** **documented** (libtorrent reference): in 2.0 the alternative backend is the single-threaded "portable C file functions" one; the multithreaded one is from 2.1. **documented/reports:** the maintainer acknowledges that memory mapping performs worse than pread/pwrite of 1.x under high cache-miss patterns such as seeding, and a user seeding from a HDD reported reads of about 1.25x the upload; **a known priority bug with POSIX and partial files exists in a 2.0 release** (project issue tracker). **measured:** the host with xfs was already at 1.00x, so the benefit in bytes may be zero; it may help latency or memory pressure. **expected:** a single thread may cap a very fast peer, so never test it on the busiest instances. **measure first.**
- **How:** check which options your client version lists; set the disk IO type through the API or UI of the test instance; it needs a restart of the client (clean shutdown so it does not recheck), in a window without copies. Pair and compare (SEC-PERF-3).
- **Rollback:** set the type back to default and restart the client.
- **Verify:** amplification and read latency, test against control, over 48 hours.
- **Don't:** test it on an instance with partial files; restart the client without a clean shutdown.

### SEC-PERF-19: No structural storage change in the hot season; verify the backup before any
- **Rule:** reformatting a store, moving images between hosts, or changing the file system happens outside the hot season, with a backup that has been read back (SEC-STOR-1, SEC-STOR-2) and a restore test of at least one VM.
- **Why:** moving several terabytes of images twice (out and back) over a 1 Gbit LAN is many hours per leg, with all affected VMs stopped (including the router if it is there) and sustained reads and writes on two disks at the worst time. There is no easy way back once formatted. The alternative of SEC-PERF-14 step 4 may remove the need.
- **How:** plan it for the cool season; list the VMs that must be offline and what stops with them; keep one live backup the whole time; rehearse the restore of one VM first.
- **Verify:** written plan with downtime per VM, a verified backup of each, and a rollback.
- **Don't:** migrate "while it is slow anyway"; start without a restore test.

### SEC-PERF-20: Restarts for tuning are rolling, one guest at a time, and stop at the first non-OK
- **Rule:** any restart needed to apply a tuning change is done one VM at a time with a driver that stops at the first result that is not OK and waits between guests (for example 30 seconds). No restart while a large copy or a VM migration is running.
- **Why:** a restart storm reproduces the recheck storm of SEC-PERF-7, and a restart during a copy or a migration gives results nobody can interpret.
- **How:** use a rolling restart script with a list of host and VM identifiers; keep each run's log; restart the client with a clean shutdown where possible.
- **Verify:** after each guest the client has all its torrents complete and none in checking.
- **Don't:** restart a group in parallel; continue after a failed guest.

### SEC-PERF-21: Remove or mark configs of guests that live on another host
- **Rule:** a host must not keep a startable configuration for a guest whose disk lives on another host. Remove it, or mark it clearly, after checking it has no leftover disks that fill the store.
- **Why:** a `qm start` by mistake would start a second copy against an image that is also in use elsewhere, or corrupt a duplicate image. Related: SEC-STOR-8 for old copies that share an address. **expected:** such duplicates were found left over from moves between two hosts.
- **How:** compare the VM list of each host (`qm list`) with the intended inventory; for each foreign config check that no disk remains in the store, then delete the config (a host mutation: with the owner's approval). Also disable port mapping (UPnP) in clients that use manual NAT, and make sure the client's open-files limit covers its file pool (`grep 'open files' /proc/<pid>/limits`).
- **Verify:** each guest id exists on exactly one host.
- **Don't:** delete a config without checking the store for its disks.

## Checklist: before the hot season
1) Airflow checked and improved on every disk bay; temperatures compared with the datasheet limit (SEC-PERF-1).
2) Bulk reads (backups, parity, scans) moved to the cool hours with a rate cap and idle IO class (SEC-PERF-2).
3) Baseline of 24 to 48 hours taken after copies and migrations ended; control VMs named; change log in place (SEC-PERF-3).
4) Each host classified as read-bound or write-bound (SEC-PERF-4); only the matching remedies chosen.
5) Slot cap, hash-check limit and, where justified, IO threads tested on pairs, then rolled out in small batches (SEC-PERF-5 to SEC-PERF-7).
6) Worst-case limits in place for VMs that can saturate a shared disk (SEC-PERF-8); service VMs protected where needed (SEC-PERF-16).
7) Thermal throttle running in dry-run with a kill switch and a monitoring item (SEC-PERF-9); time-of-day cap decided only with a week of data (SEC-PERF-10).
8) No read cache or RAM bought without the coverage curve (SEC-PERF-11, SEC-PERF-12).
9) On btrfs stores, the write ladder followed in order and measured (SEC-PERF-13 to SEC-PERF-15); no structural change this season (SEC-PERF-19).
10) Restarts only rolling; duplicate guest configs cleaned (SEC-PERF-20, SEC-PERF-21).
