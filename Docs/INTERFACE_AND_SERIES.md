# Interface and LEL series profiles

Updated 2026-10-24. One active analyzer, one serialized Modbus owner. Normal operation remains offline.

## Choosing an instrument and port

Choose Analyzer Type offers Auto Detect (default), LEL 670 Series, LEL 700 Series, BTU and FID. Old saved `LEL` selections remain readable and are presented as the corresponding series. Saving a new choice stops the old worker, invalidates readings/indicators, closes the transport, and initializes the new profile before polling resumes. Simulator generation and manual LEL series selection stay aligned.

The COM dropdown uses PySerial enumeration and shows each port description and device name. Refresh rescans without restarting. The previous choice remains visible with an unavailable label if removed. Hardware connection/test attempts require a currently enumerated port; simulation needs no serial adapter. Existing baud, timeout, identity-page and additional serial-setting fields are preserved. Physical adapters still use the documented 8N1 format.

The user authorized read-only connections on all available serial ports on2026-10-24. Normal **Connect** and **Test Connection** work directly on the selected enumerated port, without additional authorization prompts or launch flags. Saved hardware settings can resume read-only monitoring on startup. Normal connections cannot create a write-capable transport. Unavailable ports and unverified register-page/protocol definitions remain separate connection checks.

For confirmed Acknowledge/Reset on the previously authorized SNR671 controller, **Connect SNR671 / COM4** starts the same scoped bench session as the optional command-line launcher. Its command grant is held only in memory. Test Connection forces a read-only transport even during a bench session, and switching the bench connection to a different endpoint removes the command grant.

Auto Detect uses FC03 only. Recognized assembly information selects the LEL series. A positive identity conflicting with the manual family or series loads the detected interpretation, displays a warning and blocks commands. Generic PREVEX text or a version beginning with 7 does not establish 700-series identity.

## Reading and connection displays

Digital cards show parameter/register name, value and units, with `--` for unavailable values. Zero is valid. Active indicators retain their colors and names without an ON prefix; STATUS remains a single enum. Inactive indicators disappear.

The main Connection Status is green/Connection Established only after a valid current primary Modbus reply, or red/No Connection when disconnected, failed or overdue under the existing connection-loss threshold (max of five seconds and three configured poll intervals). A GUI watchdog also expires the connection if worker updates stop. A controller fault and a healthy connection can coexist.

The circular gauge keeps its last valid numeric reading for at most four seconds from that measurement's original sample time, across failed reads and the older controller's flashing numeric/fault LCD. It does not renew the timer when an old cached register word is emitted again. Retention is internally `RETAINED_STALE`, visually gray with a retained-reading label, and ends with `--`. The next valid value replaces it immediately. Profile changes and explicit disconnect clear it immediately.

This hold exists only inside the gauge widget. It never modifies worker snapshots, historian samples, trends, alarm decoding, connection health or command preflight. During a nonnumeric native fault-display phase, the small primary digital card may show `--`; only the main gauge retains the last number. The prior worker-level fault LCD cache has been removed. Actual negative and out-of-range numbers are preserved; the pointer alone stays within the arc. LEL faults retain the established -100 lower endpoint, normal operation -30, and FULLSCLE/manual positive range.

## Commands and LEDs

Commands use raised buttons with separate LEDs on their right. OFF is dark gray. A valid Modbus acknowledgment turns only the initiating button's LED green for three seconds. A rejection or failed transmission turns it red for three seconds. STATUS completion, later status updates and repeated snapshot delivery do not restart an acknowledgment LED. Disconnect/profile changes reset all LEDs.

Green means acknowledgment, not successful execution. The receipt and command audit separately record pending calibration, observed STATUS sequence, completion, failure, unconfirmed execution or unknown outcome. No command is issued on startup. Controls require a current matching identity, an Operator/Administrator session, confirmation and applicable lock/busy checks. One pending command blocks duplicates. Ambiguous outcomes are never retried automatically.

| Command | 670 word (register 8) | Simulator behavior / 700 restriction |
| --- | --- | --- |
| Acknowledge | 0x0100 | Approved simulated operation |
| Reset | 0x0200 | Approved simulated operation |
| ZERO CAL / SPAN CAL / FULL CAL | 0x0300 / 0x0400 / 0x0500 | Monitor STATUS sequence and outcome |
| ZERO TEST / SPAN TEST / FULL TEST | 0x0600 / 0x0700 / 0x0800 | Monitor STATUS sequence and outcome |
| SAVE ALL | 0x0900 | 670 acknowledgment does not prove EEPROM persistence; 700 disabled because Rev D allows factory changes |
| LOCK CAL / Unlock | 0x0F00 / 0x1000 | 670 simulated software-lock readback; 700 disabled because Rev D says Modbus lock commands have no effect |

Cold Start, internal commands, output-test bypasses and prohibited register writes remain excluded. The simulation command path emits serialized FC06 request/echo frames; physical commands cannot use it.

**Physical restriction:** the existing user-authorized COM4/SNR671 bench path still permits only individually confirmed Acknowledge and Reset. Calibration, tests, SAVE ALL, LOCK CAL and all other physical writes remain disabled. The new request prepares and tests these functions in simulation; it does not expand the physical bench allowlist. All real 700-series controls remain blocked pending validation and explicit authorization.

## Profile comparison and validation boundary

| Area | LEL 670 Series | LEL 700 Series |
| --- | --- | --- |
| Source | 670 SERIES Rev Q, especially printed pp87-93, plus retained legacy menu extract | H7FTA700 Rev D, menus pp61-68, communication/registers pp115-127 |
| Supported documented assemblies | SNR671/672/674/675 and documented D/P/K/PL variants in the existing TYPE table | SNR701/702/704/705 and each D variant, TYPE values 16-23 |
| SNR673 | Not documented; no verified conversion or operational control support claimed | Not applicable |
| Identification | ASCII 257-272, TYPE62 where supported; observed old TYPE FTA format uses the preserved conservative subset | Legacy ASCII is blank; recognized TYPE62 gates numeric VERSION40, SERIAL63 and YEAR65 reads |
| Reading factor | 0.00390625; documented D/K <=5.08 use 0.0078125 | 0.00390625; signed engineering words |
| Temperature factor | 0.24426 | 0.2442 |
| Gauges | Retained legacy menu/readouts | Independent Rev D menu, including zero/span flame temperatures29/30 |
| Status/relays/service | Existing model-specific enum and TISZ HFDW / service flags | Independent status map, extra air/fuel/service/calibrating relays, different service checks |
| Calibration lock | CAL LOCK60 when supported; old FTA support remains unverified | LOCK STATE27 controls calibration/tests |
| Configuration | Existing limits and restrictions retained | Complete independent inventory; Profile settings exposes documented safe reads grouped by menu; unvalidated/factory editing remains blocked |
| Physical status | Existing baseline; validation limited to prior controller-only read observations | Documentation implemented and simulator tested; physical hardware verification pending |

The Profile settings page exposes all documented safe register definitions, cached raw/converted values, access descriptions and restrictions, and a selected-row FC03 read. Optional pressure monitors are explicitly labeled optional; inspecting their definitions does not claim the corresponding hardware is installed. Ambiguous register106 and internal/prohibited inspections stay excluded. Settings are read-only in this release; writable manufacturer metadata is not an application write grant.

See LEL_700_REVIEW.md and VERIFICATION.md for unresolved page maps, 38400-baud timing, numeric identity behavior, optional monitors and contradictory ranges. BTU/FID register inventories and conversions are unchanged. Successful simulation and GUI checks establish software behavior only, not physical-device compatibility.
