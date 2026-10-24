# Interface improvements and named LEL series profiles (2026-10-24)

- Completed serial-port enumeration with descriptions, Refresh, saved/missing-port presentation, preservation of connection settings and rejection before opening an unavailable port. Simulation needs no COM adapter.
- Compacted digital cards by hiding redundant quality lines; unavailable remains `--`, zero remains valid. Removed ON from active indicators, kept top status/relay/service panel and corrected 700 service-relay coloring independently of relay-list positions.
- Replaced the analyzer's GOOD text with green Connection Established/red No Connection, based on current Modbus response quality. Independent GUI expiry watchdog handles an overdue worker; a controller fault does not imply failed communication.
- Replaced the prior worker LCD cache with a gauge-only four-second hold from the original sample age. Stale retained display data cannot reach historian/trends/commands. Expiry, zero/negative readings, recovery, profile resets and native TC2-fault flashing are covered. Gauge redraws only when displayed state changes.
- Added raised command buttons with independent precise three-second acknowledgment LEDs and structured receipts in simulation. Green means FC06 acknowledgment only; STATUS progress/outcome and unconfirmed/unknown execution remain separate in receipts/audit. Roles, lock checks, confirmation, duplicate blocking and no ambiguous retries remain enforced.
- Named the retained LEL baseline **LEL 670 Series**, preserving the older FTA/SNR671 compatibility subset. Added explicit **LEL 700 Series** selection alongside Auto Detect/BTU/FID. All documented 700 standard/D TYPE models and documented 670 suffixes are covered; SNR673 remains undocumented/unverified. Family/series mismatch blocks commands; generic PREVEX/firmware7 alone cannot identify700.
- Re-read the 670 Rev Q register/command tables and independent 700 Rev D menus, conversions, identity, status/relays/service, configuration and command limitations; rendered/rechecked700 p118. Kept the independent700 register inventory and temperature factor; added grouped read-only settings inspection. Corrected700 simulator CONTROL3/register33 so it does not inherit the BTU/FID aspirator-pressure seed; seeded documented700 calibration/flow/communication values. BTU/FID inventories and conversions are unchanged.
- 700 SAVE/LOCK/UNLOCK remain unavailable under Rev D's restrictions. Additional calibration/test/persistent-setting commands are functional in approved simulator profiles only. The physical COM4 exception remains confirmed Operator/Admin ACK/RESET only. No physical port was opened or real command sent during this update. 700 physical compatibility and broader670 sensor/control validation remain pending.
- Verification: **650 tests passed in65.66s**; focused relay-color/connection independence check also passed. Coverage includes all documented models, signed conversions, serial enumeration/removal, four-second retention, three-second LED expiry, acceptance vs completion, lock/role/mismatch restrictions, delayed/failed replies, recovery and real Qt670-to700-to670 worker replacement. Tests use simulation/fake clients only.
- Final Windows executable rebuilt successfully. Packaged simulation smoke passed(exit0,45 updates,41 live Diagnostics updates,max GUI heartbeat gap110ms,physical_access=false). Source smoke also passed. Dark/light and1100x780 layouts inspected for670/700D/BTU/FID; chooser and settings views rendered. Compileall,pip check and generated inventory checks passed. Evidence: tmp/interface-test-results.xml,tmp/interface-packaged-final/smoke-report.json,tmp/interface-layouts/. These are local QA artifacts, not physical validation.
- Updated README, Docs/INTERFACE_AND_SERIES.md, VERIFICATION.md and generated inventory. Previous publication hold below was resolved by explicit user approval; commits throughf5e8321 were pushed before this new update. This update is a new local milestone; hosted CI requires its publication.

# Stable HMI value during controller LCD flashing (2026-10-23; superseded display-cache design)

- Confirmed from live history that the native LCD alternates-99%LFL,TC2 FAIL and blanks. The HMI had mirrored those messages into temporary missing numeric readings.
- Added a scoped, bounded cache of the last fresh numeric fault-LCD sample. Known TC2 FAIL/blank intervals do not renew sample time. Expiry(6s at the current2s poll interval),communication loss,profile/fault changes or other menus invalidate the retained value. Fault indicators remain active and retained samples are labeled explicitly.
- Real25s HMI test passed:92 updates,81 steady-99.00 numeric samples,eight retained LCD-message updates,max heartbeat gap125ms,writes0. Full regression603 passed in26.50s,including flashing,expiry,offline/recovery,menu and device changes. Rebuilt executable smoke passed before restart. GitHub publication remains pending prior explicit approval for the supplied manual and bench notes.

# Match the real controller fault reading (2026-10-23)

- Corrected the legacy FTA fault-state display: raw8001H was being converted to approximately-128%LFL while the controller LCD showed-99. The primary reading now explicitly uses fresh LCD51–55 for this specific current fault state and displays-99.00%LFL; raw1 remains in Diagnostics. Normal signed measurements are not clamped or replaced.
- Missing, stale or non-reading LCD content produces an unavailable reading rather than a false process value. The readout names its LCD source and historian quality is INSTRUMENT_FAULT_LCD.
- Real COM4 HMI regression passed(42 updates,max heartbeat gap125ms,writes0), including-99.00 reading and-100..100 fault gauge. Final regression:602 tests passed in26.51s. Rebuilt packaged smoke passed(exit0,45 updates,max heartbeat gap125ms). Updated executable restarted onCOM4 and live historian confirms-99.0%LFL with INSTRUMENT_FAULT_LCD quality and STATUS25. GitHub publication remains blocked pending explicit permission for the supplied manual and bench notes.

# Real SNR671 HMI and operator bench controls (2026-10-23)

- Integrated user-provided670 Series Rev Q manual; reviewed printed43–46/87–93 and rendered command table90. User confirmed SNR671=LEL and explicitly requested real-controller Acknowledge/Reset tests.
- Added an explicitly granted COM4/9600/address1/PDU-1 controller session, older FTA identity parsing and a restricted compatibility profile. Newer zero-filled registers are excluded. Plain saved settings never grant physical access. Live logging is separate from simulation; injection controls are disabled for hardware.
- Real read-only HMI test:35s,129 updates,max GUI heartbeat gap125ms. Matched STATUS25/TC2 Fail,Fault relay,SERVICE00A1,alarm setpoints40/50%LFL,FULLSCLE100 and actual LCD-99%LFL. Raw process8001H remains distinguishable from LCD clamping; controller-fault data quality is explicit.
- Added only user-confirmed Operator/Admin ACK0100H and RESET0200H via dedicated bench transport. No generic physical writes/calibration/Save. Fresh identity checks, serialized pacing,audit,duplicate suppression and unknown-outcome retry blocks apply. No real ACK/RESET was executed by the agent.
- Added visual command receipt and before/after STATUS/RELAYS/SERVICE; acknowledgment is not proof of execution. User-controlled physical execution remains pending. LEL fault range adapts to-100..FULLSCLE and restores-30..FULLSCLE when Status/relay faults clear; negative sign alone never changes the scale. Numeric values outside either range remain preserved.
- Regression:601 tests passed in26.71s, including fake-client command-word/role/confirmation/timeout tests, real-traffic replay and hardware GUI guards. Final packaged smoke passed(45 updates,max heartbeat gap125ms) including serial-runtime import. Packaged HMI launched visibly onCOM4; current hardware.sqlite3 rows confirm live readings and process responsiveness. Command audit count was0 at verification. A12s adaptive-gauge hardware run also passed(40 updates,max heartbeat gap125ms,writes0). Packaging includes the managed Python ssl companion PEM required by its runtime without changing verification behavior. Details:Docs/SNR671_BENCH.md. GitHub publication awaits explicit user approval for the supplied manual and bench notes after automatic approval review rejected the publication.

# Authorized physical connection test — COM4 (2026-10-23)

- User explicitly authorized a read-only connection test. COM4(ATEN USB serial bridge) successfully communicated at9600 baud/8N1, packet address1, PDU offset-1. Seven final replies passed CRC checks; no writes or address0 requests were issued. Port released and saved application settings unchanged.
- Identity includes SNR671 and an older TYPE FTA/non-ASCII version format not handled by current Auto Detect. Full firmware/serial identification remains unverified. Registers62/63 returned0; do not infer support or model from these.
- Three samples reported STATUS25/TC2 Fail, Fault relay active, FULLSCLE100 and raw process8001H. A healthy measurement was not established. This limited successful connection does not validate commands or general hardware compatibility. Details and remaining gates are in Docs/VERIFICATION.md; raw frames remain in the local tmp test report.

# Diagnostics responsiveness fix (2026-10-23)

- Reproduced progressive GUI starvation with Diagnostics open and100 live traffic rows at1100x780. Timer gaps grew from0.5s to8.7s while the serial worker remained responsive. Tracebacks identified table cell replacement and ResizeToContents processing on the Qt thread.
- Replaced automatic content-based resizing with stable, user-resizable column widths and unwrapped cells. Reuse existing cells, update only changed text, skip unchanged table contents and restore signal/paint state after batch updates. Applied to traffic/history/event/audit tables to prevent the same repeated work there.
- Added a bounded subprocess regression exercising full100-row maximum-length frame updates, Qt timer responsiveness, mouse navigation back to Gauge and clearing/reloading the table. The subprocess timeout turns an event-loop stall into a test failure.
- Extended source and packaged smoke tests to keep Diagnostics open under live polling for12s and check heartbeat gaps, continued updates and full bounded traffic.
- Validation:587 tests passed in18.63s. Source smoke passed(39 Diagnostics updates,max heartbeat gap110ms); rebuilt executable passed(exit0,40 Diagnostics updates,max heartbeat gap125ms). Manual18s reproduction stayed around0.5s timer gaps after the fix. Diagnostics screenshot and whitespace check passed. No physical access or writes.

# Active indicator display (2026-10-23)

- Status/Relays/Service now show only current active indicators. Inactive/unavailable/stale indicators and empty category rows are hidden. Communication quality and current STATUS remain visible in the summary; stale STATUS is marked unavailable.
- Regression:586 tests passed in14.95s, including one-current-STATUS visibility and hiding all previous indicators on communication loss. Source GUI and rebuilt Windows executable smoke tests passed (13 updates,one LEL,physical_access=false). Screenshot visually checked. No physical access or writes.

# Chooser correction (2026-10-23)

- Manual LEL/BTU/FID selection now switches both the profile defaults and simulated instrument together. Reopening inconsistent saved selections repairs previous-family default names/models; custom instrument names remain intact.
- FID units/full-scale fields appear only for FID. LEL simulation generation appears only for LEL. Auto Detect retains a separate simulated-family choice. Cancel leaves stored settings untouched; OK confirms the selection.
- Replaced Save with OK. Address compatibility dynamically enforces displayed ADDRESS>=2 for minus-one mode (packet>=1), while direct mode permits1. The resulting packet address is displayed; underlying address-zero protections remain enforced.
- Regression:586 tests passed in15.08s, including actual Qt mouse selections and OK confirmation. LEL/FID chooser layouts visually inspected. Windows rebuild and packaged smoke passed (exit0,15 updates,one LEL,physical_access=false; existing test settings also exercised legacy migration). Whitespace check passed. No physical access or writes.

# Current checkpoint — single-analyzer update and full LEL manual (2026-10-23)

## Completed

- Replaced multi-device application management with one configured analyzer, one worker/transport, Auto Detect(default) or LEL/BTU/FID selection, saved serial settings and Test Connection. Original schema1 settings receive a backup before migration.
- Added read-only ASCII identification and a separately validated numeric700-series fallback. Profile mismatch/unknown identity blocks commands. Full manual H7FTA700 Rev D now drives700 menus, units, status/relay/service maps and command restrictions; legacy LEL remains separate.
- Added signed gauge minimum-30, prominent zero, preserved out-of-range numbers, live FULLSCLE preference and optional manual display range. Fixed unsigned simulator comparisons that incorrectly generated danger for negative LEL/FID values.
- Added all applicable Gauge-menu digital readouts, per-register age/quality, horizontally scrollable status/relay/service panel, right command panel, refreshed profile-specific polling and live/history plots.
- Added salted PBKDF2 local accounts/sessions with Viewer/Operator/Administrator checks, confirmed worker-side simulation commands, fresh target identity checks, calibration lock checks, duplicate/ambiguity guards, STATUS monitoring and persistent command audit.700 Lock/Unlock/Save excluded according to revised manual.
- Preserved history/CSV, alarm events, diagnostics, bounded traffic, dark/light themes, fault injection and read-only transport library. No physical port opened; no physical write API exists. Added revised operating instructions,700 manual review and verification gates.
- Windows CI updated for single-analyzer smoke testing; generated inventory includes independent700 definitions. New PDF and full extracted source retained.

## Validation

- Full local pytest regression:584 passed (latest completed full run15.05s); all I/O simulated/mocked. Includes60 new700 revision cases plus existing detection, switching, negative values, stale/offline behavior, permissions, prohibited commands and ambiguous timeout tests.
- Source GUI smoke passed for LEL700(13 updates), BTU(14), FID(14), with one detected instrument each. LEL screenshot visually reviewed; manufacturer tables119/127 rendered and checked.
- PyInstaller Windows build completed. Packaged smoke passed with exit0,13 updates, one detected LEL,10 Gauge readouts and physical_access=false. Final rebuilt executable passed again (exit0,13 updates,one LEL,10 readouts,physical_access=false).
- Dependency consistency, source compilation and the desktop environment check passed. Git whitespace check passed; hosted CI awaits push.

## Outstanding

- Physical compatibility, addressing/PDU offset,700 page map/timing, FID protocol/unit address and all manufacturer contradictions remain pending in Docs/VERIFICATION.md. Register106 is recorded but blocked due conflicting manual statements.38400 is not offered until timing validation.
- Real-hardware operation remains disabled; test results establish software behavior only. No calibration/test command is automatically retried after an unknown outcome.
- Configuration-writing UI, additional-user management UI, advanced archival/retention controls, installer/signing and clean-machine Windows10/11 acceptance remain release work.700 inventory is read-only outside the approved simulation command subset.

---

# Historical checkpoints (superseded application workflows)

# PREVEX HMI progress

## Scope and safety
Milestone 1 software foundation and Milestone 2 simulation monitoring preview implemented. No physical instruments accessed. Physical transport is read-only, unavailable from the GUI, and requires explicit authorization to open a port. Offline operation is mandatory. Missing/ambiguous hardware behavior remains gated, not claimed complete. This is not the full production release.

## Completed
- Manage Analyzers now defaults to a single-click instrument chooser that closes the dialog and opens the chosen monitoring screen. Configuration editing has a separate tab; selecting an unchanged instrument does not restart polling or discard/apply edits.
- Updated operator-screen requirement: show exactly one selected analyzer, including in simulation; the initial four-card overview is replaced. A persistent global selector switches the monitoring gauge, details, live/history trends, alarm list and device diagnostics together. All enabled analyzers continue to poll in the background.
- Added native Qt circular gauge using FULLSCLE and model-specific alarm thresholds. Unknown thresholds stay neutral; offline/stale/disabled values hide the indicator. Out-of-range numeric values are preserved. Compact windows scroll instead of clipping the gauge/chart.
- Added Qt monitoring overview, independent analyzer detail screens, family-specific engineering values, relay/service indicators and live PyQtGraph trends.
- Added saved simulation-device management (add/edit/disable/remove/sort/reorder), duplicate-address prevention and dark/light themes.
- Added threaded polling and database ownership, signal-based GUI updates, asynchronous shutdown and explicit GOOD/STALE/OFFLINE/DISABLED state. Old process values are hidden when not current.
- Added SQLite simulation historian and independent alarm/communication transition events, bounded history view and CSV export with instrument IDs. Live/history plots break at recorded communication gaps.
- Added bounded TX/RX diagnostics, per-device stats, safe manual read-only register inspection and simulated fault/recovery controls.
- Added launch scripts, operating instructions and PyInstaller Windows build configuration. No physical connection or command/control screen exists in this preview.
- CI now includes source and packaged GUI smoke tests, Windows executable build and downloadable preview artifacts.
- Implemented single-owner bus engine with transaction lock, total-bus pacing, interframe spacing, bounded raw traffic and per-device diagnostics.
- Implemented explicit addressing modes/PDU offsets, safe contiguous block reads, page boundaries and documented alternate-page byte order.
- Implemented centralized primary/ancillary/identification scheduler, cached state, stale/offline quality and bounded per-device failure backoff.
- Implemented PyModbus/PySerial read-only adapter with no write/command API; tested only with mocked clients. FID hardware path blocked pending missing protocol.
- Implemented multi-family in-memory RTU simulator with measurements, status, relays, calibration sequences and injected timeout/CRC/exception faults.
- First hosted GitHub Actions run passed: https://github.com/maple289/CIC_HMI/actions/runs/39886185541 (profile checkpoint).
- Added per-family register inventories and exact Decimal conversions, with manufacturer access separated from application write permission.
- Documented protocol pages, command exclusions, model restrictions and 17 hardware / documentation verification gates in Docs/.
- Added Windows GitHub Actions workflow: locked dependency install, pip check, Python compilation, pytest, generated-inventory consistency, offscreen Qt/plot smoke check, and retained test evidence.
- Git repository connected; three source PDFs preserved in Docs/.
- Read all three PDF extracts; captured page-separated source text in Docs/extracted/.
- Confirmed Python 3.12.14 bundled runtime; created local .venv.
- Established project foundation, pinned direct dependencies and development rules; application modules remain to be implemented.
- Installed dependencies in project-local .venv; added project VS Code interpreter settings.
- Added scripts/check_environment.py for a visible setup check and automated offscreen validation.
- Disabled automatic terminal activation in project VS Code settings after PowerShell blocked Activate.ps1. Use .venv/Scripts/python.exe directly; Windows execution policy is unchanged.

## Findings and unresolved questions
- FID PDF has only menu and conversion pages; no supplied protocol specification and no UNITS register number.
- LEL/BTU packet addresses and register-number-to-PDU offsets need read-only hardware validation.
- BTU unit, blank alarm/calibration ranges and vacuum factor require verification.
- See forthcoming Docs/REGISTER_SPECIFICATION.md and Docs/VERIFICATION.md.

## Test results
Analyzer chooser fix: 495 tests passed locally in2.49s, including an actual Qt mouse click through the modal Manage Analyzers dialog, selected-screen navigation, saved selection and no polling restart on selection alone.
Single-analyzer/gauge update: 494 tests passed locally (latest full run2.29s), covering range mapping, LEL legacy200%LFL, FID range/units, BTU low/high bands, missing thresholds, out-of-range values, hidden stale indicators, cross-page selection, selection persistence and clearing previous-device data. Four-device background polling GUI smoke passed; screenshots checked for LEL/BTU/FID, light theme and offline state. Compact-window overlap corrected with scrollable content. Rebuilt Windows executable passed its smoke test (exit0,7 updates,4 background devices,physical_access=false). Hosted CI pending for this change.
Monitoring checkpoint: 481 tests passed locally in 2.19s. Independent expected-factor cases cover every scaled register, beyond inverse-round-trip tests. Includes settings persistence/corruption, independent history stream identity, SQLite retention/quality, widgets suppressing stale values and threaded fault isolation/clean shutdown.
Source GUI smoke passed with four simulated analyzers, and overview/detail/trend/diagnostics screenshots visually inspected. Final PyInstaller rebuild passed, and packaged EXE exited0 with a PASS smoke report (7 updates,4 devices,physical_access=false). Final local regression: 481 passed in2.14s; pip check and source compilation passed. Hosted monitoring CI run is pending push at this entry.
Communication/profile foundation: 404 tests passed locally (0.76s), including thread-concurrency serialization, aggregate pacing and 16-device failure isolation/recovery. All device I/O simulated or mocked. Source compilation and whitespace checks passed.
Register/profile tests: 382 passed locally on Python 3.12.14. Includes signed boundaries and inverse conversions for every scaled definition, legacy dilution, FID units, status/relay/service mapping, unsupported registers, write restrictions and model limits. GitHub-hosted run pending push.
2026-10-22 environment smoke check: PASS on Python 3.12.14.
- Imports passed: PySide6 6.8.3, pymodbus 3.11.3, pyserial 3.5, pyqtgraph 0.13.7, numpy 2.2.6, pytest 8.4.2, PyInstaller 6.16.0.
- SQLite and JSON round trip passed.
- Qt event loop and synthetic PyQtGraph plot passed (15 timer updates); rendered window in tmp/environment-check/window.png.
- pip check: no broken requirements.
- User confirmed the visible setup-check window worked. The later monitoring tests above additionally exercise the application and packaging. Physical communications and complete release acceptance are still unverified.

## Next steps
## Remaining work
- Milestone 3: secure local user accounts and Viewer/Operator/Administrator enforcement; permission-controlled, confirmed calibration/configuration workflows; persistent command/configuration audit trail; manufacturer-validated outcome rules. These are NOT available in this preview.
- Milestone 4: richer historian ranges/retention configuration, archival/disk-capacity handling, installer/signing, clean-machine Windows10/11 validation and full release acceptance.
- Hardware: obtain missing FID protocol/UNITS documentation and resolve all VERIFICATION.md gates through explicitly authorized read-only physical testing. No physical control may be enabled based on simulator tests.
- No system-wide software installation, Windows security change, COM-port access or actual Modbus write was performed.
