# Blob storage for agent pools and GPU jobs (design)

Status: **design only, nothing built or deployed.** Waiting on the decisions of section 9, then a spike (section 8).

## 1. Why

- **Bots exchange no files today.** `tareas.py` is text only: 2 KB body, 30 lines, no attachment call. `MULTI_BOT_TASKS.md` says a file
  crosses "as a name and a hash, or as a path inside a repo both can read". That leaves the media handoff (designer -> marketing ->
  person) with no mechanism.
- **Gitea is the wrong place for blobs.** A file committed to a repo stays in history after deletion. Space comes back only after a
  history rewrite plus `git gc --prune`; Gitea's "garbage collect repos" cron runs plain gc and keeps reachable history. Issue
  attachments and release assets are freed on delete. LFS is freed only by the optional `cron.gc_lfs`, which is off by default and
  only for objects older than 7 days. (Forum reports and commit logs, not the official docs: verify against our Gitea version.)
- **The app VM's disk is small.** One 4K clip is about 200 MB, so a pool's media would fill it quickly.
- **GPU jobs push the bytes twice.** The container uploads a file to a host and downloads the result, inside one long HTTP call. When a
  host fails mid-job, the next host gets the whole upload again. With host choice by load (`ranked()` in `gateway.py`)
  retries across hosts became normal, so a shared place for job inputs pays off.

## 2. What was checked

**Hermes Agent:**
- No native S3 in file tools, the media cache, gateway attachments, memory or backups. Telegram attachments land in local cache
  paths only (`/root/.hermes/cache/images/`, `/root/.hermes/cache/documents/`).
- The marketplace lists a third-party "s3" plugin (MIT, boto3, any S3-compatible endpoint). It is a **backup** tool with tools
  `s3-ls`, `s3-pull`, `s3-push` and `s3-rm`, its maintainer is inconsistent across sources, and its code is not audited. Not used: a
  narrow `gateway` command fits better (`INTEGRATIONS_MAP.md` 3.1).
- Not verified: whether a release after our pin (v0.21.6; upstream at v0.23.0) added anything. Check at the next upstream scan.

**Self-hosted S3 servers** ([P] = read on the project's own page, the rest from secondary sources):

| Option | License | Status | Fit |
|---|---|---|---|
| MinIO CE | AGPLv3 | [P] Repo archived 2026-04-25, read-only, "no longer maintained"; source only, no prebuilt binaries or images; users are sent to the commercial AIStor. Earlier steps (console removed from CE in 2025, images stopped in Oct 2025, maintenance mode Dec 2025) come from secondary summaries. A community fork (pgsty/minio) exists. | **No.** No upstream security fixes. |
| **Garage** (Deuxfleurs) | AGPLv3 (matters only if modified and exposed) | 2.x line, `--single-node`; v2.3.0 reported 2026-04 (secondary) | **Chosen.** One binary, tens of MB of RAM (unverified). [P] Per-key, per-bucket read/write/owner grants; presigned URLs; complete multipart; lifecycle `Expiration` and `AbortIncompleteMultipartUpload` (prefix inside `Filter`). No bucket policies, no ACLs, no prefix-scoped keys. |
| SeaweedFS | Apache-2.0 | [P] 4.53 on 2026-11-08 | **Runner-up**, if prefix-scoped keys or real IAM policies become necessary. Costs: master, volume, filer and S3 processes, more RAM; space comes back by vacuum (default above 30 % garbage), and a compacting volume can fail writes briefly. |
| RustFS | Apache-2.0 | [P] 1.0.x since Sept; lifecycle and IAM fixes still landing | Too young: authorization-bypass advisories in its 1.0 alpha/beta (e.g. CVE-2026-45041). |
| Versity S3 Gateway | Apache-2.0 | v1.0.x | An S3 front over a POSIX filesystem, so objects stay browsable as files. Lifecycle and policy support not verified. |
| Ceph RGW | LGPL | Active | Too heavy for a small single node. |

## 3. Shape

```
  stack containers (the Docker host)                 blob store (own LXC, own disk, LAN only)
  gateway blob put/get/ls/link  ── S3 ──>  bucket pool-<team>   one key per stack of that pool
  gateway transcode/image/video ── S3 ──>  bucket jobs          short life, written by the gateway
                                              ^
  GPU hosts (no keys) ── presigned GET/PUT ───┘
```

- **Where:** a small dedicated LXC (or VM) with its own virtual disk, reachable only from the Docker host and the GPU hosts (firewall
  on the LXC and on the hypervisor). Not on the Docker host (disk), not on a desktop (not always on).
- **Server:** Garage 2.x, `--single-node`, replication factor 1.
- **It is an exchange area, not an archive.** Everything expires (section 5). Nothing kept only there; anything a person must keep goes
  to their own files or a backup the datamanager role owns.

## 4. Isolation

- **One bucket per pool** (the business team's bots share one; a person's stack gets its own when needed). **One access key per
  stack**, granted read+write on its pool's bucket only. Garage grants are per key and per bucket, so no key reaches another pool.
- **The trust boundary is the pool.** Without prefix-scoped keys any bot of a pool can delete what another bot of the same pool wrote.
  The gateway never overwrites or deletes another bot's object (section 6), but an agent using the key by hand could. If that matters,
  switch to SeaweedFS (prefix policies) before building.
- **GPU hosts hold no key.** The gateway hands them presigned URLs that last only for the job (section 7).
- **Keys** go into each stack's `.env` through `ops/stack_keys.py` (as other shared values), never in `gateways.json` or git. The admin
  token stays on the storage LXC.
- **Privacy class:** a pool bucket carries that pool's work (class of the pool's own data). Never a person's chat, memory or
  transcript; never another pool's data.

## 5. Life of an object

| Bucket | Expiration | Also |
|---|---|---|
| `pool-*` | 14 days (proposed) | `AbortIncompleteMultipartUpload` after 1 day |
| `jobs` | 2 days | same |

Must be tested on Garage: that an expired object's disk space is really freed (section 8).

## 6. `gateway blob` (narrow command, stdlib)

```
gateway blob put FILE [--para ROL] [--dias N]   -> blob:<sha256>/<name>  sha256=<hex>  bytes=<n>
gateway blob get blob:<sha256>/<name> OUT        streams to OUT.part, checks size and sha256, then renames
gateway blob ls [--mios]                         names, sizes, who, age (never contents)
gateway blob link blob:...  [--min M]            presigned GET for a GPU host or a LAN tool (not for people outside)
```

- **Content-addressed, immutable keys:** `<sha256>/<safe name>`. The same file uploaded twice is stored once. `put` never
  overwrites; there is no `rm` (expiry removes things). Object metadata: the uploading stack's name and the time, nothing else.
- **What crosses in a task:** the line `blob:<key> sha256=<hex> bytes=<n>`, which fits the 2 KB `tareas` body. The receiving bot runs
  `gateway blob get` and checks the hash.
- **Implementation:** AWS SigV4 signing written with the standard library (no boto3, like the rest of `gateway.py`); single PUT up
  to 64 MB, multipart above (16 MB parts, resumable); downloads stream to `.part` and are verified. Every call logs one metadata line
  (size, seconds, bucket, ok), never names or contents.
- **Delivery to a person** stays as now: `get` into the container, then `MEDIA:` to Telegram. Presigned links are never sent to
  people (the store is LAN only).
- **Skills:** the media and team skills say "hand a file to another bot as a blob, never by committing it to Gitea".

## 7. Phase 2: GPU jobs through the store

- The gateway puts the input in `jobs` once, then calls the chosen host with a presigned GET for the input and a presigned PUT for the
  output, instead of POSTing the bytes.
- If the host fails, the next host in `ranked()` order gets new URLs for the same object: no second upload from the container.
- Hosts keep accepting the old POST body, so both paths work while hosts are rebuilt.
- Hosts never hold a key; URLs last about the job's estimate plus a margin.

## 8. Spike before building (about 30 min, then one day for expiry)

On the desktop with Docker, Garage 2.x single node:
1. Two buckets and two keys: key A cannot list, read or write bucket B.
2. Presigned GET and PUT from another machine on the LAN.
3. A multipart upload of a few GB from a GPU host, resumed after an interruption.
4. An `Expiration` rule of 1 day: the next day, the objects are gone and `df` shows the space back.
5. RAM and CPU of the idle and busy server.

## 9. Open decisions for the operator

1. Garage instead of MinIO (MinIO CE is archived).
2. A new LXC for it, and its disk size.
3. Retention: 14 days for pool buckets, 2 days for `jobs`.
4. Later: move Gitea's own attachments and LFS to the same store (Gitea supports `STORAGE_TYPE = minio`; the endpoint is written as
   `host:port`).
