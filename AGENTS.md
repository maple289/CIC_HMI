# PREVEX HMI development rules

- Manufacturer PDFs in `Docs/` are authoritative; record uncertainty in `Docs/VERIFICATION.md`.
- Physical hardware access requires explicit user authorization. Default physical transports remain read-only. The user-authorized SNR671 COM4 bench exception permits only confirmed Operator/Administrator Acknowledge and Reset (670 Rev Q p90); no other physical writes or generic bypass.
- Never use address zero, broadcast commands, Cold Start, internal commands, or registers prohibited for Modbus writes.
- One serialized transaction owner per shared bus. Apply bus-wide traffic limits and bounded per-device backoff.
- Keep GUI work on the Qt thread and serial I/O off it. Mark stale/offline measurements explicitly.
- Simulated tests do not establish hardware compatibility.
- Update PROGRESS.md with test evidence and outstanding work. Commit meaningful milestones.
- Install dependencies in the local virtual environment only. Do not install system software or alter Windows security settings.
