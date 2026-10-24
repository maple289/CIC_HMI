# PREVEX HMI development rules

- Manufacturer PDFs in `Docs/` are authoritative; record uncertainty in `Docs/VERIFICATION.md`.
- The user explicitly authorized read-only connections on all available serial ports on 2026-10-24; normal Connect/Test Connection require no additional authorization prompt. Open only the selected enumerated port, not every port. Default physical transports remain read-only.
- The user subsequently approved expanding physical controls for manufacturer-validated firmware: documented register8 Acknowledge/Reset, ZERO/SPAN/FULL CAL, ZERO/SPAN/FULL TEST, SAVE ALL and LOCK/UNLOCK, with role checks, explicit per-command confirmation, fresh matching identity and applicable lock/busy checks. Do not execute real commands during agent development/testing. The provisional SNR6714.81 remains limited to its existing COM4 confirmed ACK/RESET exception until applicable command/lock behavior is verified.700 physical controls remain unvalidated. No generic register-write bypass.
- Never use address zero, broadcast commands, Cold Start, internal commands, or registers prohibited for Modbus writes.
- One serialized transaction owner per shared bus. Apply bus-wide traffic limits and bounded per-device backoff.
- Keep GUI work on the Qt thread and serial I/O off it. Mark stale/offline measurements explicitly.
- Simulated tests do not establish hardware compatibility.
- Update PROGRESS.md with test evidence and outstanding work. Commit meaningful milestones.
- Install dependencies in the local virtual environment only. Do not install system software or alter Windows security settings.
