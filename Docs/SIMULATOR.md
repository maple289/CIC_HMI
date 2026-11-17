# Simulator and transport limits

## Development-only use (2026-11-16)

Simulation is no longer an operator mode. Diagnostics, Connection Settings and
Choose Analyzer Type provide no simulation controls. Saved simulation preferences
migrate to disconnected hardware mode without discarding the selected serial
endpoint or existing historical databases. Historical simulation recordings retain
their provenance and remain accessible for viewing, backup and export.

The source/development build supports an explicit isolated check:

```powershell
.venv/Scripts/python.exe scripts/run_hmi.py --smoke-test --data-dir tmp/development-simulation
```

Source tests use `tests/dev_support.py` to explicitly authorize the in-memory
transport. Other callers must opt in through `allow_simulation=True` when loading
test settings and `simulation_authorized=True` when constructing a worker/window.
The protected native build has a compiled production policy: it rejects that
transport even with the constructor flag, and does not expose the simulator CLI.
Its `--production-smoke-test --data-dir tmp/production-startup` checks disconnected
hardware-only startup without creating a monitoring worker or opening a port.
Neither automated check sends real analyzer commands.

## Test model

The desktop application owns one active analyzer and one serialized polling session. The reusable in-memory bus can still emulate multiple devices for library regression tests, including16-device backoff/isolation. It opens no COM port, socket or virtual serial driver.

Profiles cover legacy LEL, Rev D700 LEL, BTU and FID independently.700 LEL returns blanks for removed257+ identification and exposes numeric62/40/63/65 identity. Gauge parameters and relay/service/status maps depend on model/revision. FID UNITS remain explicit context; BTU units remain unverified. Simulated PDU offset is configured, not hardware evidence.

Changing measurements, signed negative values, peaks, calibration stages, STATUS and relay flags are modeled. Faults include timeout, corrupt CRC, protocol exceptions, unknown identity and lost command acknowledgment after execution. Normal recovery follows bounded exponential poll backoff. Primary1..4 has priority; Gauge fields are polled at the requested interval subject to bus capacity, ancillary registers more slowly. Each displayed register has its own staleness indication.

Confirmed, permission-checked simulator commands use the same BusEngine transaction lock and pacing as reads. They are never routable to a physical write. Fresh identity, target, actual calibration lock and duplicate guards precede sending. Calibration stages last2s for test purposes; this is not analyzer timing. Locks/Save are excluded for700 because Rev D changed their behavior. Only simulated sequences support completed-simulated outcomes; unproven operations stay sent/unverified or unknown. Audit/history are local SQLite records.

The simulator does not reproduce all hardware latches, interlocks, input priorities, pressure-monitor options or failure combinations. It is a test model, not proof of physical compatibility. Real calibration/test commands may suppress alarms or move gas valves; hardware safety remains independent.

The default PyModbus/PySerial physical adapter is read-only, with retries0 and configurable timeout(default0.5s). The operator can explicitly connect the selected enumerated port; startup does not connect automatically. Separately authorized670 controls retain identity, role, confirmation, lock, busy, pacing, readback/audit and no-retry restrictions.700/BTU/FID physical writes remain unvalidated; prohibited writes remain blocked. No generic register-write bypass exists. Simulator/fake-adapter tests do not validate physical protocol applicability; consult VERIFICATION.md for the distinct read-only hardware evidence.

Tests cover independent exact factors, signed words, model/revision identities, enum/bit decoding, documented read windows, forbidden registers/commands, active profile switching, stale/offline GUI state, roles/password hashing, duplicate/ambiguous command handling, audit trails, total bus pacing, serialized ownership, fault backoff/recovery and packaging smoke tests. None validates electrical RS485, USB-converter timing or real firmware behavior.
