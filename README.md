# PREVEX HMI

[![Windows CI](https://github.com/maple289/CIC_HMI/actions/workflows/ci.yml/badge.svg)](https://github.com/maple289/CIC_HMI/actions/workflows/ci.yml)

Offline Windows monitoring for CIC PREVEX LEL, BTU and FID analyzers. Development in progress; physical-device compatibility is unverified. The initial physical transport will remain read-only. No hardware access is part of automated testing.

**Serial-port access:** the user has authorized read-only connections on all available serial ports. Choose an available port, then use Connect or Test Connection without additional authorization prompts or launch flags. Only the selected port is opened. Operating writes require the supported, individually confirmed command workflow below.

**Operating controls:** supported670 actions require sign-in, individual confirmation and fresh identity/lock/status checks; SAVE ALL requires Administrator. Firmware is informational under the user's manufacturer-confirmation policy.700/BTU/FID physical writes remain unvalidated. See [command readiness](Docs/COMMAND_READINESS.md) and [verification gates](Docs/VERIFICATION.md).

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
- [Launch, hardware operation and Windows build](Docs/OPERATING.md)

Manufacturer PDFs in `Docs/` are the authority for analyzer behavior. The new full [LEL700 Rev D review](Docs/LEL_700_REVIEW.md) explains differences from the legacy LEL extract. Simulator assumptions must never be presented as proof of physical compatibility.

## Continuous integration

GitHub Actions runs on pushes to `main`, pull requests and manual dispatch. The Windows/Python 3.12 job installs pinned dependencies, checks their consistency, compiles Python files, runs pytest, checks generated register tables and renders both setup and monitoring GUI smoke tests. Test reports and smoke-test images are retained as workflow artifacts for 14 days. CI requires Internet for dependency installation; normal HMI operation does not.
## Current application

One active analyzer and one serialized polling connection. **Choose Analyzer Type** offers Auto Detect, LEL, BTU and FID. Normal startup is disconnected and hardware-only; use **Connect to Analyzer** or **Test Connection** with the selected enumerated port. The dashboard appears after identification and live acquisition. Firmware is informational; actual model/series selects the register definitions.

Monitor, Service and Diagnostics retain the signed gauge, compact readings, active indicators, confirmed command/setting workflows and audit. Trend, recording, historical sessions and CSV export remain in the independent Trend window and are accessible offline. Simulator controls and simulation source choices are absent from the operator UI; development testing retains the explicit harness described in [SIMULATOR.md](Docs/SIMULATOR.md).

Physical connections default to read-only. Separately authorized670 controls retain fresh identity/status/lock checks, sign-in and per-action confirmation; SAVE ALL requires Administrator.700/BTU/FID physical writes remain unvalidated and prohibited registers remain blocked. Historical scoped bench results are documented in [verification gates](Docs/VERIFICATION.md), not alternative production launch instructions. See [operating instructions](Docs/OPERATING.md) and [command readiness](Docs/COMMAND_READINESS.md).

## Analyzer selection

Auto Detect, LEL, BTU and FID are the functional choices. Internal650/670/690/700 definitions retain manufacturer-specific registers, conversions and restrictions. Firmware is informational. See [functional profile behavior and migration](Docs/FUNCTIONAL_PROFILES.md).

## Protected Windows releases

The existing development package remains available. Native-compiled protected one-file/one-folder builds, the custom icon, encoded About attribution, offline integrity checks and optional Windows certificate signing are documented in [Release protection and signing](Docs/RELEASE_PROTECTION.md). Build-only dependencies are in `requirements-release.txt`; signing certificates/private keys must stay outside Git. Current unsigned builds do not claim a verified Windows publisher.

## Hardware-only operator interface

The operator application offers Auto Detect/LEL/BTU/FID and starts disconnected. Simulation source/injection controls have been removed. Valid older simulation preferences migrate to hardware without discarding saved connection settings or historical recordings. The protected release rejects developer simulator/bench flags; source tests use an explicit development harness. See [release procedures](Docs/RELEASE_PROTECTION.md).
