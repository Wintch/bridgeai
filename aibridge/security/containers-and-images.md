---
title: Containers and images (hardening, networks, databases, agents, backups)
scope: Docker/Compose hosts and the containers on them, including containers that run AI agents and per-person or per-client stacks
when_to_use: writing or reviewing a compose file; a container needs a port, a key or a database; adding a stack for a person or a client; a hardening change is proposed; deciding who may use Docker on a host
related: [README.md, policies.md, patching.md, firewall-and-ports.md, detection-and-audit.md]
---
# Containers and images

A container is a process with a fence around it, and the fence is only as strong as what you configured and verified. Start from a baseline (read-only root, no capabilities, no new privileges, limits, non-root), check what the process really received instead of what the YAML says, try every hardening change on a throwaway container first, and keep secrets, databases and backups out of the blast radius. Image scanning and rebuilds live in [patching.md](patching.md) (SEC-PATCH-17, SEC-PATCH-18); credentials and AI-agent rules live in [policies.md](policies.md) (SEC-POL-5, SEC-POL-6, SEC-POL-11). The generic firewall pattern is in [firewall-and-ports.md](firewall-and-ports.md) (SEC-FW-3, SEC-FW-4).

## Quick decision table

| Situation | Do | Rule |
|---|---|---|
| Writing a new compose service | Start from the baseline: read-only, tmpfs, `cap_drop: ALL`, `no-new-privileges`, user, limits | SEC-CONT-1 |
| A hardened container breaks | Add back one capability at a time, keep the reason in a comment | SEC-CONT-2 |
| "Is it really hardened?" | `docker inspect` plus `/proc/1/status`, not the YAML | SEC-CONT-3 |
| About to change hardening on a live service | Trial it on a throwaway container with a smoke test | SEC-CONT-4 |
| Fixed something inside a running container | It is lost on recreate: change the image or a mount | SEC-CONT-5 |
| Someone asks for Docker access on a host | Treat it as root on the host | SEC-CONT-6 |
| Adding `ports:` to a service | Bind a specific IP, filter in DOCKER-USER | SEC-CONT-7 |
| Per-person, per-client or agent stack | Internet yes, LAN no, explicit pinholes | SEC-CONT-8 |
| A database container needs to be reachable | Never all interfaces, never a superuser app role | SEC-CONT-9 |
| An agent container needs to reach another machine | Forced-command key + firewall pinhole, not a prompt | SEC-CONT-10 |
| A privileged script reads files an unprivileged side can write | `O_NOFOLLOW`, regular file only, size cap | SEC-CONT-11 |
| A script loads a `.env` file | Parse it as data, do not `source` it | SEC-CONT-12 |
| Referencing or rebuilding an image | Digest pin plus a dated rollback tag | SEC-CONT-13 |
| "Where is the backup?" | Off the VM, restore drilled | SEC-CONT-14 |

## Rules

### SEC-CONT-1: Give every service the same hardening baseline
- **Rule:** every compose service starts with: read-only root filesystem with `tmpfs` for the paths that must be writable, `cap_drop: [ALL]`, `no-new-privileges`, a non-root `user` when the image allows it, CPU/memory/pids limits, and no Docker socket mount. Each deviation gets a comment saying why.
- **Why:** most container escapes and post-exploitation steps need a writable root, extra capabilities, setuid binaries or a fork bomb to work. Removing them costs a few lines and makes a compromised service much less useful to an attacker. A service that is root on purpose (for example to read root-owned files) can still be read-only with two capabilities.
- **How:**
  ```yaml
  services:
    <service>:
      image: <image>@sha256:<digest>          # SEC-CONT-13
      user: "<uid>:<gid>"                     # omit only if the image needs root; say why
      read_only: true
      tmpfs: [/tmp]                           # add only paths the app must write (pid file, cache)
      security_opt: ["no-new-privileges:true"]
      cap_drop: [ALL]
      cap_add: []                             # SEC-CONT-2: one line per proven need
      ports: ["<host-ip>:<host-port>:<container-port>"]   # SEC-CONT-7
      volumes:
        - ./<config>:/etc/<app>/<config>:ro   # mount everything read-only unless it must be written
      deploy:
        resources:
          limits: { cpus: "0.5", memory: 64M, pids: 128 }
  ```
  If hardening is kept in a separate override file (a way to leave a shared template untouched), every script that creates the container must pass that file, or a hand-run `docker compose up` recreates it unhardened. Prefer folding the baseline into the main file, or make the override the only way to launch and check with SEC-CONT-3 after every recreate.
- **Verify:** SEC-CONT-3 on every running container, after every recreate.
- **Don't:** mount `/var/run/docker.sock` into an app or agent container (it is root on the host, SEC-CONT-6); use `privileged: true`, `seccomp=unconfined` or `apparmor=unconfined` to "make it work"; run the baseline on paper only.

### SEC-CONT-2: Drop all capabilities, add back only what a test proves is needed
- **Rule:** start from `cap_drop: [ALL]`. When something fails with "operation not permitted", find the capability it needs, add exactly that one, and write the reason next to it.
- **Why:** Docker's default set (about 14 capabilities) includes things few services use. A short, justified list is reviewable; "it works with the defaults" is not.
- **How:** run the service's real workload (not only start-up) on a throwaway container (SEC-CONT-4) and read the log for `operation not permitted`. Typical mapping: `CHOWN`/`FOWNER`/`DAC_OVERRIDE` for file ownership and permission work on mounts; `SETUID`/`SETGID` for a process that drops privileges or calls `initgroups`; `KILL` for signalling other users' processes; `NET_RAW` for `ping`, `tcpdump`, `nmap`; `NET_BIND_SERVICE` only for ports below 1024 (prefer a high port instead).
- **Verify:** SEC-CONT-3 shows exactly the list you wrote, nothing more, nothing less.
- **Don't:** add `SYS_ADMIN`, `NET_ADMIN` or `SYS_PTRACE` to fix a failure without understanding it; they are close to "privileged". Do not leave a capability in "because it was needed once".

### SEC-CONT-3: Verify what the process really got, not the YAML
- **Rule:** after creating or changing a container, read the effective settings from the running container: `docker inspect` for the host-config side and `/proc/1/status` inside for what the kernel applied. A script that does this and exits non-zero on a mismatch is worth keeping next to the compose file.
- **Why:** the compose file says what you asked for. A typo in a key, a Compose version that ignores `deploy.resources.limits.pids`, or a launch without the override file leaves the YAML looking hardened and the container not.
- **How:**
  ```bash
  docker inspect -f 'ro={{.HostConfig.ReadonlyRootfs}} priv={{.HostConfig.Privileged}} sec={{.HostConfig.SecurityOpt}} pids={{.HostConfig.PidsLimit}} mem={{.HostConfig.Memory}}' <container>
  docker exec <container> cat /proc/1/status | grep -E '^(CapEff|CapBnd|NoNewPrivs|Seccomp):'
  capsh --decode=<CapEff-hex>        # on the host (package libcap2-bin): names the capabilities
  docker exec <container> id
  ```
  `NoNewPrivs: 1` means `no-new-privileges` is in effect. `CapEff` is the effective set of PID 1: for a root process it equals the capabilities you added; for a non-root process it is usually empty and `CapBnd` (the ceiling) is the one to compare. If `PidsLimit` is `0` or `-1`, the limit did not apply; set `pids_limit:` at service level and re-check.
- **Verify:** the output matches the profile: `NoNewPrivs: 1`, the exact capability list, a pids limit within your maximum, not privileged, seccomp and AppArmor not switched off.
- **Don't:** declare a container hardened because the compose file has the keys, or because a scanner (Trivy) passed: image scanners do not look at container configuration (SEC-PATCH-17). A stopped or sleeping container cannot be checked: start it and check again.

### SEC-CONT-4: Trial a hardening change on a throwaway container first
- **Rule:** before applying a new profile to a service people use, create a disposable copy from the same compose files plus the new settings, run a smoke test, and delete it. Only then touch the real one.
- **Why:** a dropped capability or a read-only root breaks things in ways start-up does not show: a stop path that writes state, a tool that needs a raw socket, a cache directory that no longer exists. The trial is where you find out, instead of the people using it.
- **How:**
  - Name it with a fixed prefix (for example `hardtest`) and make the script refuse any other name, so it can never act on a real stack.
  - Use the same compose files as production plus the new profile; give it no real secrets (empty API keys), keep it out of schedulers and wake/sleep managers, publish at most one port on the LAN IP behind a random password.
  - Smoke test two kinds of checks. Positive: the health endpoint, outbound HTTPS, DNS, writing to each data directory, `chown` in a work directory, the tools the service needs. Negative: things the profile must now refuse (`mknod` fails; a setuid copy of `id` does not become root).
  - Include a stop and start (the SIGTERM path often flushes state with fewer privileges), then grep the container log for `operation not permitted|permission denied|EPERM`.
  - Wait for a slow first boot (1-3 minutes) before calling anything failed, and print that you are waiting.
  - Tear down: files written by a root container are root-owned, so delete them from a container, not with `rm`.
- **Verify:** SEC-CONT-3 on the trial; the smoke test prints all PASS; the log has no permission errors.
- **Don't:** trial on a copy that has the operator's keys; treat the first failing check as a profile failure before ruling out a still-booting container or a wrong expectation (an API that correctly answers 403 to an anonymous caller is a pass).

### SEC-CONT-5: Persist changes in the image or a mount, never in the running container
- **Rule:** anything that must survive goes into the Dockerfile (then rebuild, SEC-PATCH-18) or into a bind mount or named volume. A package installed or a file edited inside a running container lives in its writable layer and is lost on the next recreate.
- **Why:** recreates are routine (config change, image update, restart policy). An `apt upgrade` run inside a live container "worked" and vanished at the next recreate; the fixed package never reached the image.
- **How:** `docker diff <container>` lists what exists only in the layer; move each item that matters into the image or a mount. To prove persistence, recreate on purpose and re-check the version: `docker compose up -d --force-recreate <service>`, then `docker exec <container> <tool> --version`.
- **Verify:** the evidence of the fix (version string, file hash) is present after a deliberate recreate, and the image on disk is newer than the fix date (SEC-PATCH-18 audit).
- **Don't:** accept an agent's "patched" for a container without checking the image and the package log after a recreate (SEC-POL-11, SEC-DET-14).

### SEC-CONT-6: Treat the docker group as root
- **Rule:** membership in the `docker` group, access to the Docker socket, or permission to run `docker run` is root on the host. Grant it only to people who already have root, and list the members on every review.
- **Why:** `docker run -v /:/host <image>` gives a read-write view of the host, including `/etc/shadow` and every key. A deploy account that "only has docker" and a scoped sudo rule for one command add no extra restriction.
- **How:**
  ```bash
  getent group docker                                   # who is root-equivalent
  sudo gpasswd -d <user> docker                          # remove someone who does not need it
  # containers that mount the socket:
  docker ps -q | xargs -r docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}' | grep docker.sock
  ```
  For per-project isolation, rootless Docker (needs `subuid`/`subgid` ranges for the user: `grep <user> /etc/subuid`) is possible; `userns-remap` changes ownership of bind-mounted files and can break stacks that write as root, so test it first. A temporary scanner container that needs the socket (SEC-PATCH-17) is removed after the run.
- **Verify:** every member is accounted for, and no long-running container has the socket mounted.
- **Don't:** treat a service account with a deploy key and docker membership as "unprivileged"; its key is a root key and should be restricted accordingly (SEC-POL-6, SEC-POL-7).

### SEC-CONT-7: Publish ports on one specific IP and filter in DOCKER-USER
- **Rule:** write published ports as `<host-ip>:<host-port>:<container-port>` (use `127.0.0.1` when only a local proxy needs it). Remember that `ports:` bypasses ufw/host INPUT rules; restrict reachability in the `DOCKER-USER` chain.
- **Why:** `"3000:8080"` binds all interfaces, and published-port traffic is forwarded, so host firewall rules on INPUT never see it. Without a DOCKER-USER policy every `-p` is open to whoever can route to the host.
- **How:** the generic default-deny pattern is SEC-FW-4 and the dead-man switch and atomic load for it are SEC-FW-1 and SEC-FW-3 in [firewall-and-ports.md](firewall-and-ports.md). Container-specific points: allow `ESTABLISHED,RELATED` first, because replies leave with the bridge's address; end the chain with a DROP; load the whole chain atomically with `iptables-restore --noflush`; re-run the loader after creating a new Docker network, because rules that depend on a subnet are not added by themselves.
  ```bash
  docker ps --format '{{.Names}} {{.Ports}}' | grep -E '0\.0\.0\.0|\[::\]'     # published on every interface
  ss -ltnp
  ```
- **Verify:** the list above is empty (or each line is justified), and a port scan from another network segment shows only what you intend.
- **Don't:** rely on ufw to protect a published port; do not publish a port for a service only another container uses (use the compose network).

### SEC-CONT-8: Give guest and tenant containers internet but no LAN
- **Rule:** containers that run what a person or an agent asks for (per-person stacks, guest instances, tools such as `nmap`) live on their own Docker network, may reach the internet, and may not reach the LAN, other Docker networks, or the host. Exceptions are explicit pinholes: one source subnet, one destination host, one port, each commented.
- **Why:** such a container is effectively a user shell on your network. Without the rule it can see the router, the database host, the GPU box and the other tenants.
- **How:** carve all guest networks out of one reserved range (`<guest-cidr>`), then in the `DOCKER-USER` chain, in this order: `ESTABLISHED,RELATED` accept; pinholes (`-s <stack-subnet> -d <lan-host> -p tcp --dport <port> -j RETURN`); drop from `<guest-cidr>` to every RFC 1918 range, `100.64.0.0/10` and `169.254.0.0/16`; accept the rest of `<guest-cidr>` (the internet); then your LAN rules; final DROP. Add INPUT rules so guests cannot reach services on the host itself (accept `ESTABLISHED,RELATED` first, because the host's own health checks to a guest's port come back through INPUT). Keep addresses in a root-owned config file outside git, validate every pinhole line before touching iptables (a typo must not leave the chain half built), and load the chain in one atomic restore.
  A stack that must reach its own helper on the host (a wake-on-demand service, for example) gets a pinhole from that stack's subnet to that gateway address and port only.
- **Verify:** from inside a guest: internet works; the LAN router, a LAN host and another guest time out. `iptables -S DOCKER-USER` shows the order above. After creating a stack, the pinhole exists (reload the firewall unit).
- **Don't:** add a broad pinhole "to test" and forget it; allow a whole host instead of one port. A timeout (not a refusal) from a guest to its own helper usually means the pinhole is missing.

### SEC-CONT-9: Databases are never published on all interfaces, and apps never use a superuser role
- **Rule:** a database container publishes no port, or one bound to a specific IP; its `pg_hba.conf` (or equivalent) allows named networks, not `all`; and the application connects with a role that has only the privileges it needs, never the superuser.
- **Why:** a database on every interface is one firewall mistake away from the internet, and an application SQL injection or stolen DSN with a superuser role is a database-wide (and sometimes host-level, via `COPY ... PROGRAM`) compromise.
- **How:**
  ```yaml
  ports: ["<lan-ip>:5432:5432"]     # or remove the line and use the compose network
  ```
  ```sql
  CREATE ROLE <app_role> LOGIN;                  -- then \password <app_role>  (prompts; nothing in shell history)
  GRANT CONNECT ON DATABASE <db> TO <app_role>;
  GRANT USAGE ON SCHEMA public TO <app_role>;
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO <app_role>;
  GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO <app_role>;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO <app_role>;
  ```
  Use a separate migration role if the app runs DDL. Narrow `pg_hba.conf` from `host all all all scram-sha-256` to the LAN CIDR and the Docker network, after copying the original; turn on connection logging so you learn who connects; reload without restart:
  ```bash
  docker exec -u postgres <db-container> cp -p <data-dir>/pg_hba.conf <data-dir>/pg_hba.conf.bak-<date>
  docker exec -u postgres <db-container> psql -c "ALTER SYSTEM SET log_connections = on;" -c "SELECT pg_reload_conf();"
  ```
  Switch the application's DSN to the new role, with the password in a secret file (SEC-POL-5).
- **Verify:** `docker port <db-container>` shows a specific IP or nothing; `psql -c "SELECT rolname FROM pg_roles WHERE rolsuper;"` lists only the admin role, and the app's DSN is not it; a connection from a network outside `pg_hba` is refused; the log shows the real client addresses.
- **Don't:** treat "the firewall only lets the LAN in" as the whole defense; do not put the DB superuser password in an app `.env`; do not change `pg_hba.conf` without a backup copy and a tested rollback (restore the file, `SELECT pg_reload_conf();`).

### SEC-CONT-10: Never give an agent container a full-shell key or cloud token and rely on its prompt
- **Rule:** whatever a container can read, the agent inside it (or a prompt injected into it) can use. Give it only credentials whose power is limited by a real control: a forced-command SSH key, a per-service token with minimal scope, a firewall pinhole to one host and port. Instructions in a prompt or skill text are not a control (SEC-POL-11).
- **Why:** an agent that is told "use only the provided tools" will still use a shell key that happens to be mounted if that is the shortest path, or if a web page or file tells it to.
- **How:** on the target machine, an `authorized_keys` line such as
  ```
  restrict,command="<dispatcher-script>" ssh-ed25519 <public-key> <purpose>
  ```
  where the dispatcher validates the requested action against an allowlist, and logs it. One key per purpose and per stack. Reach the target only through a pinhole (SEC-CONT-8). Provider API tokens are scoped to one resource (SEC-POL-6, SEC-POL-7); a cloud console or account-wide token never goes into an agent container. A regex blocklist of "dangerous commands" in the agent is a guard rail, not a refusal: show the full command in the approval prompt.
- **Verify:** list mounts and environment of the container (`docker inspect -f '{{json .Mounts}}' <container>`, look for `.ssh`, `.aws`, `.config`, token files); from inside, try the key with a command other than the intended one and confirm it is refused or routed to the dispatcher.
- **Don't:** mount the operator's own SSH directory or a shared deploy key; allow the agent "read" access to a secrets directory; treat a successful smoke test of the intended tools as proof that nothing else works.

### SEC-CONT-11: Privileged readers open user-writable files defensively
- **Rule:** a root-owned process (waker, scanner, deploy hook, backup) that reads a file from a directory that an unprivileged user or an agent can write must open it without following symlinks, must refuse anything that is not a regular file, must cap the size, and must not hang.
- **Why:** with a plain `open()`, the writer can plant a symlink to another tenant's secret (the reader adopts it) or a FIFO (the reader blocks forever). The reader's privilege becomes the writer's.
- **How:**
  ```python
  import os, stat

  def read_small(dir_path, name, limit=4096):
      dfd = os.open(dir_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
      try:
          fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
      finally:
          os.close(dfd)
      try:
          st = os.fstat(fd)
          if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
              raise ValueError("not a small regular file")
          return os.read(fd, limit)
      finally:
          os.close(fd)
  ```
  Run the check on the opened descriptor (`fstat`), not on the path before opening (that is a race). Put a timeout around anything that talks to a socket or pipe. Better still: keep inputs for privileged readers in a directory only root can write.
- **Verify:** a test that plants a symlink and a FIFO in the directory and confirms the reader rejects both without blocking.
- **Don't:** check `os.path.isfile(path)` and then `open(path)`; read the whole file when a few KB is expected; trust that "only our agent writes there".

### SEC-CONT-12: Load env files as data, never `source` them
- **Rule:** a script that reads a `.env` file parses `KEY=value` lines; it does not `source` or `eval` the file.
- **Why:** a value containing `;`, `$(...)` or backticks runs as code when the file is sourced. Keys and tokens pass through many hands and sometimes through command-line arguments.
- **How:**
  ```bash
  load_env() {                         # usage: load_env <file>   (values stay literal; no quote stripping)
    local line
    while IFS= read -r line || [ -n "$line" ]; do
      [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
      export "${line%%=*}=${line#*=}"
    done < "$1"
  }
  ( umask 077; printf '%s\n' "<KEY>=<value>" > <stack-dir>/.env )   # umask scoped to this one write
  ```
  Scope `umask 077` to the single write (subshell); a `umask` left on for the rest of a provisioning script made later files `0600` and broke a service that needed to read them.
- **Verify:** put `x=$(touch /tmp/pwned)` as a value in a test env file and run the script; `/tmp/pwned` must not exist.
- **Don't:** `. ./.env` or `source` a file you did not write line by line; export secrets into a shared shell session.

### SEC-CONT-13: Pin images by digest and keep a rollback tag
- **Rule:** third-party images in compose are referenced by `@sha256:<digest>` (with the pull date in a comment). Your own images get a dated rollback tag before every rebuild. Rebuild procedure and scanning are SEC-PATCH-18 and SEC-PATCH-17.
- **Why:** a tag such as `<image>:<version>` is moved by the publisher; the next recreate may run a different image than the one you tested. A digest never moves, so it also goes stale: schedule the review.
- **How:**
  ```bash
  docker pull <image>:<tag>
  docker image inspect --format '{{index .RepoDigests 0}}' <image>:<tag>     # paste as <image>@sha256:<digest>
  docker tag <image>:latest <image>:prev-$(date +%F)                          # before rebuilding your own image
  ```
  Rollback: retag `prev-<date>` as `latest` and recreate (SEC-CONT-3 afterwards). Move off base tags whose distribution release is out of support rather than pinning them.
- **Verify:** the running container uses the pinned image (`docker inspect -f '{{.Image}}' <container>` equals `docker image inspect -f '{{.Id}}' <image>@sha256:<digest>`); a periodic audit flags digests that differ from what the registry serves and too many `prev-*` tags.
- **Don't:** use `latest` for anything you did not build; keep unlimited rollback tags.

### SEC-CONT-14: Backups must leave the VM
- **Rule:** a backup on the same disk, VM or host as the data is a convenience copy, not a backup. Keep an encrypted copy on another machine, include the configuration that is not in git (firewall config, env files, certificates), and drill a restore.
- **Why:** disk failure, ransomware, a deleted VM or a compromised hypervisor take the data and the copy together. A restore never tried is a guess.
- **How:** have the backup host pull (so the source cannot delete its own history), for example `rsync -a --partial <user>@<host>:<backup-dir>/ <dest>/` from the backup machine with a restricted key (SEC-CONT-10 pattern), or an encrypted archive tool with an off-site target. Alert on free disk space (a nightly backup fills disks quietly). Test the restore into a scratch location and compare a checksum or a record count.
- **Verify:** the newest copy off the VM is less than a day old; a restore from it was performed this quarter; losing the VM does not lose the firewall config or the keys needed to read the backup.
- **Don't:** count a second directory on the same disk; put the backup encryption key only on the machine being backed up.

## Checklist for a new or changed container service

1) Baseline in place: read-only + tmpfs, `cap_drop: ALL`, `no-new-privileges`, user, limits (SEC-CONT-1).
2) Capabilities added back one by one, each commented (SEC-CONT-2).
3) Tried on a throwaway container with a smoke test and a stop/start (SEC-CONT-4).
4) Verified on the real container: `docker inspect` and `/proc/1/status` (SEC-CONT-3).
5) Ports bound to a specific IP; nothing on `0.0.0.0` by accident (SEC-CONT-7).
6) Tenant/guest networks: internet only, pinholes explicit and commented (SEC-CONT-8).
7) No Docker socket, no full-shell key, no cloud token in agent containers (SEC-CONT-6, SEC-CONT-10).
8) Databases not published on all interfaces, application role is not a superuser (SEC-CONT-9).
9) Persistent changes are in the image or a mount; recreate once to prove it (SEC-CONT-5).
10) Image pinned by digest, rollback tag kept, scan accepted (SEC-CONT-13, SEC-PATCH-17, SEC-PATCH-18).
11) Backup exists off the VM and a restore was drilled (SEC-CONT-14).
