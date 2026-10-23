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
