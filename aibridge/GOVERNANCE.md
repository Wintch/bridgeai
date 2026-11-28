# Who decides what: owners, decision layers, and what a decision must bring

Without this, work gets confused: what we do and why. Every area has one owner; the operator is moved up to ever more general decisions,
never asked to judge details they cannot judge, and every decision they take comes with its justification and a time for tests.

## Roles

| Role | Owns | Does not |
|---|---|---|
| **Operator** | purpose and priorities, money, people's data, what is exposed to the internet, new people / machines / accounts, policies (retention, inactivity, keys) | implementation details |
| **bridgeai agent** (the coding agent on the build machine) | code, tests, images, deploys inside the pipeline's checks, hosts-only changes, docs, measurements; brings the operator's decisions as proposals | network, router, the operator's keys, spending |
| **back** (the infrastructure agent) | router, DHCP and address blocks, forwards, the door, the wake service, the Proxmox hosts and disks | the bots' code |
| **tecnico bot** (to come) | post-deploy validation on test machines, self-heal proposals | choosing or rating models (the central side does that) |
| **Finance** (to come: a finance bot built on budgetai) | every spend (development time, rented compute, keys, hardware): a line with amount, purpose and owner, approved by everyone it concerns before it is spent | technical choices |
| **People and testers** | their own data and settings; their consent for what touches them | the installation |

Requests between roles go as notes with a reply (`local-notes/para-back-*.md` and `respuesta-back-*.md` today), so each answer is on record.

## Decision layers

| Layer | Who | Examples | Record |
|---|---|---|---|
| **L0 within the rules** (nobody asked) | the owner | tests, a hosts-only deploy, after-batch checks, a known-problem draft, a measurement | the deploy log, the changelog |
| **L1 do, then tell** | the owner, the operator told after | a bots deploy that passed every check, a regression fix, docs | the changelog ("For the bots" first) |
| **L2 propose, the operator decides** | the owner proposes | spending; archiving or deleting a person's data; opening a port or a public service; a new machine, person or account; a policy change; anything that cannot be undone | the decision note, with the packet below |
| **L3 direction** | the operator | goals, product, who the installation is for | the plans |

## The packet of an L2 proposal

1. **What and why**, in one line each, in plain words.
2. **Cost**: money, energy, time (ours and the people's).
3. **Risk**: what can go wrong and who is affected.
4. **Test period**: where it is tried first (the guest, one stack, a canary, the test bench), for how long, and how we know it worked
   (the measure that must hold).
5. **Undo**: how, and how long it takes.
6. **Owner**: who does it and who answers for it.

A proposal without a test period or an undo is not ready to be decided.

## Who owns each area

| Area | Owner | Approves | Recorded in |
|---|---|---|---|
| Code, images, deploys | bridgeai agent | the pipeline's checks (L0/L1); the operator when it touches data or exposure (L2) | CHANGELOG.md, deploys.log |
| Machines (desktops) | bridgeai agent (`place.py`) + back (address, forwards, door) | operator for a new machine | `gpu-host/places/ACCESS.md` + the private inventory |
| Network, router, door, wake service | back | operator for anything public | the router runbook (private) |
| People's data (archive, slim, delete) | operator, with the person | operator (L2) | `ops/ARCHIVE_INACTIVE.md` |
| Keys and secrets | operator | operator | their key manager |
| Spending | finance | everyone it concerns | the finance ledger (to come) |
| Validation after deploys | tecnico (to come) | the central side judges for now | `ops/FEATURE_MAP.md` |
| Energy | bridgeai agent measures and reports | operator decides the trade-offs | `OBSERVABILITY.md` 7.2 |
