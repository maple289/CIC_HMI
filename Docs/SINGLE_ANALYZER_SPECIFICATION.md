# Replacement single-analyzer specification (2026-10-23)

This supersedes the application's multi-device operator workflow. Exactly one device configuration, transport and polling session are active. Reusable multi-device library tests remain as bus-serialization regression tests, not an application feature.

## Manual comparison

Update: the full H7FTA700 Rev D manual supersedes the legacy LEL extract for700-series units. See LEL_700_REVIEW.md for all menu/protocol differences. The LEL row below describes legacy instruments only.700-series GAUGES are1/2 plus38/39/9/24/15/11/29/30; numeric identification uses62/40/63/65 because257+ was removed.

Reviewed source PDFs directly: LEL PDF pages 2/3/4/7 (printed 86/87/88/91), BTU pages 1/2/3/4/7 (69/70/71/72/75), FID pages 1..5 (37..41). The supplied FID file is named FID_Menu_registers.pdf, not Menu_registers.pdf. Existing rendered table images and extracted source text remain in the project. PDFs are unchanged.

| Family | GAUGES menu numbered entries | Identity |
| --- | --- | --- |
| LEL | READING1, output-adjusted copy50, STATUS2, PEAK HI38, PEAK LOW39, HSG TEMP9, SET TEMP24, FLOW15, LOW FLOW23, CHK FLOW42 (read only), FLAME11 | ASCII257..272; TYPE62 supplements assembly |
| BTU | READING1/copy50, STATUS2, PEAK HI38, PEAK LOW39, HSG TEMP9, SET TEMP24, CELL VAC10, SET VAC23, FLAME11, ASP PRES33 | ASCII257..272 |
| FID | READING1, STATUS2, PEAK HI38, PEAK LOW39, HSG TEMP9, SET TEMP24, CELL VAC10, SET VAC23, ASP PRES33, FLAME11, RAW RDNG12 | ASCII257..288 |

BTU's GAUGES table also has an unnamed42 entry saying not to write via Modbus; meaning/conversion remain unknown. Show unavailable, never poll it or invent a parameter. FID has no SERVICE59 in the supplied PDF. Preserve all family-specific conversion factors, including the questionable BTU vacuum factor. Negative values remain signed; sign alone is not a fault. STATUS is one enum; relay/service bits add independent indicators.

## Identification and safety

FC03 identity probe reads257..272 first; extend to273..288 only after recognizing FID. Parse ASCII markers, assembly and version; extract serial only from explicit serial labels or the documented FID trailing serial pattern. A production year is not a serial number. Unknown/conflicting text is not a match. LEL TYPE62 can supplement/cross-check assembly. Use explicit packet address and PDU offset; never scan/write/broadcast at address0. Alternate low-byte pages require an explicit documented page choice; no speculative byte swapping.

Auto Detect is default. Manual fallback is allowed, but unresolved/unknown identity or a selection mismatch blocks commands. Test Connection performs identification/read-only checks and does not start polling or enable commands. Stop and invalidate before switching/reconnecting. No physical serial port is opened by the GUI until separately authorized hardware integration; physical writes remain absent. Full FID serial protocol and UNITS address remain missing.

## Gauge range

Negative display endpoint defaults to -30 engineering units; zero is a labeled marker inside the arc. Positive endpoint prefers valid FULLSCLE3. Manual fallback/override affects the display only. FID conversion always requires valid instrument FULLSCLE3; a display override does not alter readings. Out-of-range numbers are preserved while the position marker stops at the scale endpoint.

## Commands

Only0x0100..0x0900 plus0x0F00/0x1000 from the reviewed allowlist. No Cold Start, remote button emulation, internal-use or generic write controls. Local authentication and worker-side permission checks are mandatory. Confirm target/name/code, verify identity, status, communication and calibration lock, issue once, audit and observe STATUS. No automatic retry after ambiguity. Save/ack/reset do not have a unique documented STATUS success signature: report sent/unverified rather than claim success. Software lock can be checked through CAL LOCK60. Simulator status sequences are software models only.

For700-series units, use LOCK STATE27 rather than legacy CAL LOCK60. Save0900 and Lock/Unlock0F00/1000 are disabled because Rev D changes their behavior. No new relay/gas/zero-adjust commands are enabled.
