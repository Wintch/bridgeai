---
name: proxmox
description: "Read-only look at the Proxmox VE host: nodes, machines, RAM, disks, backups, failed tasks: `gateway proxmox`. Only where the operator configured it."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [proxmox, pve, vm, homelab, backup, monitoring, read-only]
---

# Proxmox (read-only)

When the operator asks how the servers or virtual machines are doing, which one uses the most RAM, whether a disk is
filling up or whether the backup ran, run in the terminal:

- `gateway proxmox` (or `estado`): each node (CPU, RAM, uptime), machines on/off, the five using the most RAM, every
  disk with its use (⚠️ from 85 %), and failed tasks of the last 24 h.
- `gateway proxmox vms`: every VM and container with status, CPU, RAM, uptime.
- `gateway proxmox vm ID`: one machine in detail (CPU, RAM, network and disk traffic, lock).
- `gateway proxmox backups`: the scheduled backup jobs, the last runs with their result and length, and machines that
  no job covers.

It is read-only by design: a PVEAuditor token, GET requests on a short list of paths, and the host's certificate pinned.
You cannot start, stop, change or log into anything, and you must not try another way (ssh, the web UI, curl with other
paths). For an action, say what you found and what you would do, and let the operator do it.

If it prints "no está configurado", this stack has no Proxmox access: say so, nothing else. If it says the token has no
permission or the certificate does not match, report exactly that; the operator fixes it.
