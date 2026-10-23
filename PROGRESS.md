# PREVEX HMI progress

## Scope and safety
Milestone 1 in progress. No physical instruments accessed. Physical transport will be read-only, unavailable from the initial simulation GUI, and require explicit authorization to open a port. Offline operation is mandatory.

## Completed
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
Register/profile tests: 382 passed locally on Python 3.12.14. Includes signed boundaries and inverse conversions for every scaled definition, legacy dilution, FID units, status/relay/service mapping, unsupported registers, write restrictions and model limits. GitHub-hosted run pending push.
2026-10-22 environment smoke check: PASS on Python 3.12.14.
- Imports passed: PySide6 6.8.3, pymodbus 3.11.3, pyserial 3.5, pyqtgraph 0.13.7, numpy 2.2.6, pytest 8.4.2, PyInstaller 6.16.0.
- SQLite and JSON round trip passed.
- Qt event loop and synthetic PyQtGraph plot passed (15 timer updates); rendered window in tmp/environment-check/window.png.
- pip check: no broken requirements.
- This checks the development environment, not the HMI application, packaging, physical communications, or full acceptance criteria. Visible VS Code launch remains for the user to verify.

## Next steps
Implement serialized scheduler, read-only serial adapter, simulator and communication tests; then monitoring GUI. Hardware verification remains pending; this is not yet a complete Milestone 1.
