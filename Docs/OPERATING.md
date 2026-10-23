# Running the monitoring preview

## Start

Open `scripts/run_hmi.py` in VS Code with the project `.venv/Scripts/python.exe` selected, then click Run Python File. Alternatively double-click `scripts/launch_windows.cmd`. PowerShell activation is not required.

The application opens in **SIMULATION MODE**, with an amber banner on every page. There is no physical-port connection or operational-control UI. Synthetic values are not process readings. This preview must not be used for safety functions.

## Pages

- Overview: all configured analyzers, current process values, explicit communication quality and last successful update age. Offline/stale/disabled devices show `--`, never a cached reading as current. Click a card for details.
- Analyzer details: family-specific cached registers, raw and engineering values, relay/service indications, identification and a live plot. Unsupported values are omitted or explicitly unavailable. FID UNITS are simulated context; BTU measurement unit remains unverified. Static settings and slow measurements may arrive later than process values.
- Live trends: selected analyzer, mouse-wheel zoom and drag pan. Up to 1800 points per instrument; communication gaps break the line.
- History / CSV: select instrument and time range, load up to the latest 5000 primary readings, export exactly those rows with instrument identification. UTC is preserved in tables/CSV; plots show local time. This is an initial historian UI, not an unlimited report exporter.
- Alarm / event history: latest 500 operating-state and communication transitions; independent of measurement logging. Does not replace hardware alarms/interlocks.
- Diagnostics: aggregate/per-device poll and error counts, response timing, TX/RX frames and safe read-only register inspection. Apply a simulated timeout/CRC/protocol fault, or `none` to restore responses. Recovery follows scheduler backoff and may take up to 60 seconds.

Manage analyzers from Overview: add, edit, enable/disable, remove and move up/down to save card order. Duplicate enabled packet addresses are rejected. Disabled devices remain visible. Poll intervals are requested intervals subject to bus load; 16 analyzers do not imply 1 Hz updates. Primary process/status reads have priority over ancillary parameters and identification. Under overload, slower fields can be delayed. Family, assembly and software version are explicit simulator settings.

Dark/light theme is saved per user. Toggle measurement logging in the simulated-device editor. This monitoring preview does not include user-account management, configuration writes, calibration controls or physical operation; those are Milestone 3 work.

## User files and offline operation

Qt's Windows AppLocalDataLocation stores settings.json, simulation.sqlite3 and rotating application.log files under the user's local application data folder. The exact path appears in the status bar. Nothing is written into the protected executable installation directory. All normal operation is local: no network requests, subscriptions or AI services. The simulation database is explicitly named and must never be mixed with future physical data.

Settings are saved atomically; malformed settings are reported and preserved. Measurements are retained 90 days; event history is retained independently. Live buffers and raw traffic are bounded; traffic holds 500 entries (latest 100 visible). Application logs rotate at 2 MB with 3 backups. SQLite disk-capacity handling, archival, richer retention controls and unlimited exports remain release work.

## Build and verify

From Windows Python 3.12 x64 with requirements-lock.txt installed:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe scripts\run_hmi.py --smoke-test --data-dir tmp\monitoring-smoke
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm build_windows.spec
```

Launch `dist/PREVEX-HMI/PREVEX-HMI.exe`. Distribute the entire PREVEX-HMI folder, including `_internal`, not just the EXE. The build is unsigned; signing and an installer package remain release tasks. Validate on a clean Windows machine before distribution; development-machine success is not Windows 10 certification or physical-device validation.

CI runs dependency/test/render checks on Windows. No physical COM port is opened by tests. Hardware gates and future authorized bench procedure are in VERIFICATION.md; simulator limitations are in SIMULATOR.md.
