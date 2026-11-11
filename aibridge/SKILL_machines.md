---
name: machines
description: "The person's remote machine (a PC they rent with credit, only where the operator gave them an account): its state, the credit left and a screenshot with `gateway maquina`; turning it on, entering and letting go are the person's own /machine commands (prendé mi PC, quiero jugar en la máquina, cuánto crédito me queda, включи компьютер, turn on my remote machine)."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [machines, remote-desktop, credit, power, moonlight]
---

# Remote machines (rented with credit)

Only where the operator gave this person an account on the machine-power service. If `gateway maquina` answers that it
is not configured, say so in one sentence and stop. The names of the machines are the ones the command prints; never
mention a MAC, an address or the name of the service.

## What you can run

- `gateway maquina lista`: each machine (off, on, on but not answering, busy with someone else, in maintenance, yours
  since how long) and the credit line. Run it first when they ask about their machine.
- `gateway maquina saldo`: the credit. If the service does not report it yet, the command says so: repeat that, never
  guess a number.
- `gateway maquina captura NOMBRE`: a picture of the machine's screen, only while it is theirs and on. Send it with the
  `MEDIA:` line the command prints, and ask if it is what they expect. Do not describe it with vision unless they ask.

## What only the person can do

Turning it on spends their credit, entering hands out the way in, letting it go cuts their session. You cannot do any
of them: the command you run only prints what the person has to type. Give them the exact command and the cost
sentence, in their language:

1. **Turn it on:** `/machine on NOMBRE yes`. It reserves the machine for them and wakes it; it can take a minute or two.
   If it answers that it is still starting, they type the same command again: it is not charged twice.
2. **Look before entering:** `/machine shot NOMBRE` (or you run `gateway maquina captura NOMBRE`). Entering needs a
   screenshot from the last 10 minutes, so they see the machine is the one and in the state they expect.
3. **Enter:** `/machine enter NOMBRE yes`. The way in (Moonlight, or a link) goes straight to them; you do not see it,
   so never promise it or make one up.
4. **When they are done:** `/machine off NOMBRE yes`. It suspends the machine and releases it so it stops spending. Remind
   them once when they say they finished, or when it has been theirs for hours: a machine that stays theirs keeps
   spending, nothing lets it go by itself.

## Rules

- Never reboot: it is not available, tell them to ask the operator if the machine does not answer.
- A machine "on but not answering" may have someone inside: never suggest turning it off or on.
- Busy with someone else or in maintenance: say so and offer to check later; do not retry in a loop.
- Do not put the credit, the machine names or what they did on it into memory notes.
