# PREVEX HMI progress

## Scope and safety
Milestone 1 software foundation complete; monitoring GUI next. No physical instruments accessed. Physical transport is read-only, unavailable from the initial simulation GUI, and requires explicit authorization to open a port. Offline operation is mandatory. Missing/ambiguous hardware behavior remains gated, not claimed complete.

## Completed
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
Communication/profile foundation: 404 tests passed locally (0.76s), including thread-concurrency serialization, aggregate pacing and 16-device failure isolation/recovery. All device I/O simulated or mocked. Source compilation and whitespace checks passed.
Register/profile tests: 382 passed locally on Python 3.12.14. Includes signed boundaries and inverse conversions for every scaled definition, legacy dilution, FID units, status/relay/service mapping, unsupported registers, write restrictions and model limits. GitHub-hosted run pending push.
2026-10-22 environment smoke check: PASS on Python 3.12.14.
- Imports passed: PySide6 6.8.3, pymodbus 3.11.3, pyserial 3.5, pyqtgraph 0.13.7, numpy 2.2.6, pytest 8.4.2, PyInstaller 6.16.0.
- SQLite and JSON round trip passed.
- Qt event loop and synthetic PyQtGraph plot passed (15 timer updates); rendered window in tmp/environment-check/window.png.
- pip check: no broken requirements.
- This checks the development environment, not the HMI application, packaging, physical communications, or full acceptance criteria. Visible VS Code launch remains for the user to verify.

## Next steps
Proceed to Milestone 2 monitoring GUI: overview, independent detail pages, live trends, simulated device management and diagnostics. Hardware verification remains pending. Roles, physical control, full historian UX and release acceptance remain future milestones.
