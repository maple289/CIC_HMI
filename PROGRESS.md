# PREVEX HMI progress

## Scope and safety
Milestone 1 software foundation and Milestone 2 simulation monitoring preview implemented. No physical instruments accessed. Physical transport is read-only, unavailable from the GUI, and requires explicit authorization to open a port. Offline operation is mandatory. Missing/ambiguous hardware behavior remains gated, not claimed complete. This is not the full production release.

## Completed
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
