# Work sheet: TUG2 · Kitchen, laundry and bathroom sockets (4A)

Job: Example building, GF + 4 floors (EXAMPLE) · Status: UNDER REPAIR · Assigned to: Technician B · Survey of 2026-11-15

![isolated plan of TUG2](sheet_TUG2.png)

## Lock out before touching anything

**C2 "TUG2 KITCHEN, LAUNDRY AND BATHROOM SOCKETS" (MCB 2P C16) in TS-4A: TSG apt 4A · phase L1 · sub-main 2×16 mm² + PE 16 mm², ≈ 20 m, ΔU ≈ 0.71 %**

Upstream: ID1 (RCD 2P 40 A 30 mA type A) → Q1 (SWITCH 2P 40 A) → ID0-4A (RCD 2P 40 A 300 mA type A) → Q0-4A (MCB 2P C32)

## Outlet points (6)

| Point | Type | Room | Height | Status | Note |
|---|---|---|---|---|---|
| a24 | Double socket outlet 2P+E | Kitchen 4A | 1.1 m | ok | countertop |
| a25 | Double socket outlet 2P+E | Kitchen 4A | 1.1 m | ok | countertop |
| a26 | Double socket outlet 2P+E | Kitchen 4A | 0.3 m | ok | fridge and microwave (sockets for fixed appliances, ELEC-CIR-7) |
| a29 | Socket outlet 2P+E 10 A | Laundry 4A | 1.2 m | fault | washing machine; damp box with a loose terminal (see TUG2 notes) |
| a30 | Socket outlet 2P+E 10 A | Laundry 4A | 1.2 m | ok |  |
| a33 | Socket outlet 2P+E 10 A | Bathroom 4A | 1.2 m | ok | outside zones 0, 1 and 2 (ELEC-ESP-3) |

## Measurements

- 2026-11-14 insulation: 0.4 MOhm FAIL

Pending:

- Insulation resistance with a megohmmeter, de-energized, loads disconnected (ELEC-MED-4, ELEC-EQU-2)
- PE continuity to every outlet point (ELEC-MED-3)
- RCD trip with a tester from a socket outlet on this circuit, when re-energizing (ELEC-MED-6)

## Lockout checklist (never work live)

- [ ] Switch off C2 and, if the panel is opened or there is any doubt, also the main switch (Q0-4A); the incoming terminals of the main switch stay live (ELEC-SEG-3).
- [ ] Your own padlock and tag on the device: one padlock, one person, one key; if there are several of you, a lockout hasp (ELEC-SEG-4, ELEC-EQU-21).
- [ ] Prove the voltage tester on a live source, verify absence of voltage IN EVERY BOX before opening it (L-N, L-PE, N-PE) and prove the tester again (ELEC-SEG-5, ELEC-EQU-25).
- [ ] Shared boxes: treat any cable of another circuit as live (ELEC-PLA-16).
- [ ] Warn the team before using the megohmmeter: it is also a voltage source (ELEC-EQU-27).
- [ ] Measure what is pending with the circuit dead and send the values to the agent (ELEC-MED-3, ELEC-MED-4, ELEC-PLA-20).
- [ ] When finished: boxes closed, tools out, remove only your own padlock and report; the person in charge re-energizes (ELEC-SEG-7, ELEC-EQU-17).

## Notes

insulation 0.4 MΩ: box of laundry socket a29 damp with a loose terminal; the box and the stretch up to a30 are being replaced

## When finished

`gateway electricidad plan status building-4-floors TUG2 repaired --tech "NAME" --note "..."`

_For guidance only, built from the survey: it does not replace the drawing signed by a licensed professional (ELEC-PLA-21). The sheet does not prove that the circuit is dead._
