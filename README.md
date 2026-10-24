# PREVEX HMI

[![Windows CI](https://github.com/maple289/CIC_HMI/actions/workflows/ci.yml/badge.svg)](https://github.com/maple289/CIC_HMI/actions/workflows/ci.yml)

Offline Windows monitoring for CIC PREVEX LEL, BTU and FID analyzers. Development in progress; physical-device compatibility is unverified. The initial physical transport will remain read-only. No hardware access is part of automated testing.

## Development environment

Use Python 3.12 x64. Create a project-local environment and install locked development dependencies:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe scripts\check_environment.py
& .\.venv\Scripts\python.exe scripts\run_hmi.py
```

Activation is optional; these commands work without enabling PowerShell scripts. In VS Code, select `.venv/Scripts/python.exe` as the interpreter. The environment check displays synthetic data only.

## Specification and progress

- [Manufacturer register specification](Docs/REGISTER_SPECIFICATION.md)
- [Complete per-family inventory and statuses](Docs/REGISTER_TABLES.md)
- [Ambiguities and pending hardware checks](Docs/VERIFICATION.md)
- [Progress, test evidence and next steps](PROGRESS.md)
- [Launch, simulation operation and Windows build](Docs/OPERATING.md)

Manufacturer PDFs in `Docs/` are the authority for analyzer behavior. The new full [LEL700 Rev D review](Docs/LEL_700_REVIEW.md) explains differences from the legacy LEL extract. Simulator assumptions must never be presented as proof of physical compatibility.

## Continuous integration

GitHub Actions runs on pushes to `main`, pull requests and manual dispatch. The Windows/Python 3.12 job installs pinned dependencies, checks their consistency, compiles Python files, runs pytest, checks generated register tables and renders both setup and monitoring GUI smoke tests. Test reports and smoke-test images are retained as workflow artifacts for 14 days. CI requires Internet for dependency installation; normal HMI operation does not.
## Current preview

One active analyzer and one polling connection. **Choose Analyzer Type** offers Auto Detect, LEL, BTU and FID. New installations simulate a700-series LEL analyzer using the full Rev D manual; legacy LEL simulation remains selectable. The Gauge page has a signed circular scale, manufacturer-specific digital readouts, status/relay/service indicators and a confirmed command panel. Local Viewer/Operator/Administrator checks and command audit records protect simulator controls.

Physical connections and writes remain disabled. Test Connection identifies the simulated unit without enabling controls. Live/history trends, CSV export, diagnostics, fault injection and SQLite recording remain available. See [operating instructions](Docs/OPERATING.md) and [replacement specification](Docs/SINGLE_ANALYZER_SPECIFICATION.md).

## Authorized real SNR671 bench session

Open the authorized legacy controller with `scripts/launch_controller_bench.cmd` or `PREVEX-HMI.exe --controller-com4-bench`: COM4,9600/8N1,address1,read-only monitoring plus only confirmed Operator/Admin Acknowledge and Reset. Other physical writes remain blocked. See [bench evidence and command-result display](Docs/SNR671_BENCH.md). Use the read-only launcher when commands are not required. Close an existing bench instance before launching another.
# Interface and LEL series update (2026-10-24)

The single-analyzer HMI now offers Auto Detect, **LEL 670 Series**, **LEL 700 Series**, BTU and FID, plus an enumerated serial-port dropdown with Refresh. Compact digital cards and active indicators accompany a red/green Connection Status display. The main gauge has a four-second display-only hold; retained readings never become new historian or command-input samples.

Raised command buttons have individual three-second acknowledgment LEDs. Documented calibration/test commands are exercised in simulation, with execution tracked separately through STATUS and the audit log. Physical access still defaults to read-only; the previously authorized SNR671/COM4 exception remains limited to confirmed Operator/Administrator Acknowledge and Reset. Real 700-series controls are disabled pending hardware validation. SNR673 behavior is undocumented and is not claimed as supported.

See [Interface and series guide](Docs/INTERFACE_AND_SERIES.md), [700-series manual review](Docs/LEL_700_REVIEW.md), and [verification gates](Docs/VERIFICATION.md). Profile settings provides read-only access to documented parameters and restrictions. BTU/FID register definitions and conversions remain unchanged.
