# SNR671 real-controller bench session

The user authorized live monitoring of the disconnected older SNR671 LEL controller on COM4 and requested Acknowledge and Reset buttons. The full `670 SERIES Rev Q.pdf` is now included as the670-series reference. Reviewed PDF47–50 and91–97 (printed43–46 and87–93); PDF94/printed90 command table was rendered and visually checked.

## Endpoint and identity

Verified endpoint: COM4,9600 baud,8N1,packet1,PDU offset-1. The controller's ADDRESS21 also reads1, contrary to the manual's minus-one addressing statement. This observation applies to this endpoint only; no address0 is ever used.

Identity is TYPE FTA, version-looking4[byteA7]81, assemblySNR671. The user confirmed SNR671 is LEL. The parser preserves the original text and uses a provisional4.81 context; it does not claim fully verified firmware identification or invent a serial number. The later TYPE62/SERIAL63 registers return0 and are excluded from the older compatibility profile rather than interpreted as valid data. Internal40, newer scale57/lock60/model62 and unverified alternate pages are excluded from inspection/polling for this endpoint.

## Matched readings and indicators

The35s live HMI run received129 updates with a maximum GUI heartbeat gap125ms. No writes were sent.

| Signal | Raw observed | HMI interpretation |
| --- | --- | --- |
| STATUS2 |25|TC2 failed; expected with disconnected temperature-control thermocouple |
| RELAYS4 |0004H|Fault active |
| SERVICE59 |00A1H|CHK_FLOW,CHK_RDNG,AIR_FUEL active |
| FULLSCLE3 |100|100%LFL positive gauge range |
| WARNING5 / DANGER6 |10240 /12800|40 /50%LFL |
| SET TEMP24 |246|60.08796°C using exact0.24426 factor; display60.09°C |
| FLOW15 / FLAME11 |0 /0|Zero reported values; not proof of healthy sensors |
| LOW FLOW23 |815|1.40942840SL/min |
| CHK FLOW42 |1226|2.12019536SL/min |
| Process1 |8001H|Observed fault-state word; use current LCD reading for the primary fault display, retain raw word in Diagnostics |
| Output-adjusted copy50 |27136|106%LFL, including analog fault override |
| LCD51–55 |ASCII|Controller displays-99%LFL; primary fault reading is explicitly labeled LCD51–55, with raw1 retained in Diagnostics |

Every hardware readout labels the controller fault independently of GOOD communications. Live history uses `hardware.sqlite3`; simulation data remains in `simulation.sqlite3`.

## Command authorization and evidence

670 Rev Q printed90/PDF94 explicitly defines register8 Acknowledge0100H and Reset0200H. CONTROL1/2 returned1/2 but are separate registers; they do not override the documented command-word encoding. All other physical commands/configuration writes remain prohibited. No generic write API is offered. The baseline read-only adapter remains read-only; a separate explicitly granted bench transport exposes only these two operator operations at device1/PDU7.

Each action requires local Operator/Administrator login, current communications, matching selected profile, fresh matching controller identity and a Yes confirmation naming the real controller and side effects. Requests are serialized with polling, paced, sent once, and audited. Duplicate attempts are suppressed; ambiguous outcomes prevent retries until reviewed/reconnected. Calibration locks do not block ACK/RESET per printed43, but busy/calibration/warmup states are blocked conservatively.

Acknowledge can silence the horn, clear Service Needed and adjust CHK FLOW. Reset can clear corrected latched faults, adjust CHK FLOW and initiate ignition when Flameout is active. It will not repair the disconnected assembly. Agent validation did not execute either real command; the user can test through the confirmed HMI buttons.

The command-result card reports waiting, controller replied, state changed/unchanged, rejected or unknown. It shows before/after STATUS,RELAYS,SERVICE and a timestamp. A valid FC06 echo proves a matched response, not successful execution. Observed state changes are displayed separately; an unknown result is never presented as accepted or retried.

## Launch

Use `scripts/launch_controller_bench.cmd` for the authorized bench session, or run the packaged EXE with `--controller-com4-bench`. Sign in/create a local administrator to enable only Acknowledge and Reset. Plain application launches do not inherit hardware authorization from saved settings.

For monitoring without commands use `scripts/launch_controller_readonly.cmd`, or `--read-only-com4`. COM4 is owned by one worker; close the previous bench instance before starting another. Simulation injection is disabled in hardware mode.

Full physical compatibility, unconnected sensor measurements, calibration, output wiring and other firmware functions remain unvalidated. Software/replay tests do not establish these properties.

## Adaptive gauge and final validation

During a current LEL status/relay fault the negative scale endpoint becomes-100%LFL; when the fault clears it returns to-30%LFL. The positive endpoint continues to use FULLSCLE3(100 on this unit). Stale fault flags and a negative measurement alone do not expand the scale. Genuine out-of-range measurements are never clamped. For this observed legacy fault state only(FTA profile,8001H,current Status/Fault relay), the primary gauge reads the fresh controller LCD51–55 and shows-99.00%LFL. If the LCD is stale, missing or showing another menu, the reading is unavailable rather than falsely converting the fault word to-128%. The raw word remains in Diagnostics. Normal-state signed measurements retain their original conversion. Historian quality marks derived fault-LCD readings as INSTRUMENT_FAULT_LCD.

Final regression:601 tests passed, including fault/normal scale transitions,operator-only hardware exception,fake command replies/state effects,timeout/no-retry behavior and UI receipt rendering. The12s live HMI test passed(40 updates,max heartbeat gap125ms); the35s run also crossed periodic identity revalidation. Packaged smoke passed with serial-runtime import(45 updates,max heartbeat gap125ms). The packaged interactive bench session is connected and responding; hardware.sqlite3 contains fresh physical readings. No real ACK/RESET was executed by the agent.
