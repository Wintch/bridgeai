# Work sheet: ACU1 · Pool pump

Job: House with the panel from the photo (EXAMPLE) · Status: UNDER REPAIR · Assigned to: Technician B · Survey of 2026-11-15

![isolated plan of ACU1](sheet_ACU1.png)

## Lock out before touching anything

**P26 "PILETA" (MCB 2P C10) in TP: Main panel (garage)**

Upstream: ID1 (RCD 4P 63 A 30 mA) → CG (MCB 4P C40)

## Outlet points (1)

| Point | Type | Room | Height | Status | Note |
|---|---|---|---|---|---|
| p69 | Pump | Garden | 0.3 m | fault | pool pump shed |

## Measurements

- 2026-11-14 insulation: 0.2 MOhm FAIL

Pending:

- Insulation resistance with a megohmmeter, de-energized, loads disconnected (ELEC-MED-4, ELEC-EQU-2)
- PE continuity to every outlet point (ELEC-MED-3)
- RCD trip with a tester from a socket outlet on this circuit, when re-energizing (ELEC-MED-6)

## Lockout checklist (never work live)

- [ ] Switch off P26 and, if the panel is opened or there is any doubt, also the main switch (CG); the incoming terminals of the main switch stay live (ELEC-SEG-3).
- [ ] Your own padlock and tag on the device: one padlock, one person, one key; if there are several of you, a lockout hasp (ELEC-SEG-4, ELEC-EQU-21).
- [ ] Prove the voltage tester on a live source, verify absence of voltage IN EVERY BOX before opening it (L-N, L-PE, N-PE) and prove the tester again (ELEC-SEG-5, ELEC-EQU-25).
- [ ] Shared boxes: treat any cable of another circuit as live (ELEC-PLA-16).
- [ ] Warn the team before using the megohmmeter: it is also a voltage source (ELEC-EQU-27).
- [ ] Measure what is pending with the circuit dead and send the values to the agent (ELEC-MED-3, ELEC-MED-4, ELEC-PLA-20).
- [ ] When finished: boxes closed, tools out, remove only your own padlock and report; the person in charge re-energizes (ELEC-SEG-7, ELEC-EQU-17).

## Others working now

- IUG9 (Outdoor lights, rear (garden)): Technician A

## Notes

2026-11-14 Technician B: low insulation; suspected cable buried without conduit up to the pump shed

## When finished

`gateway electricidad plan status house-panel-photo ACU1 repaired --tech "NAME" --note "..."`

_For guidance only, built from the survey: it does not replace the drawing signed by a licensed professional (ELEC-PLA-21). The sheet does not prove that the circuit is dead._
