# Functional analyzer profiles

Updated 2026-11-14. The user reports manufacturer confirmation that Modbus registers and commands are consistent across firmware revisions within each series. The application therefore uses series capabilities; this is not a new claim of physical validation for every model or operation.

## Selection and identity

Choose Analyzer Type and Connection Settings offer Auto Detect, LEL, BTU and FID. LEL contains internal670/700 definitions; BTU uses690 and FID uses650. A reliable model/TYPE selects the actual series. Generic PREVEX text alone cannot select700. Model/family conflicts, unknown models and invalid identification remain visible and block controls as appropriate. Firmware is informational: missing or unreadable data displays Unknown. The observed FTA `4§81` identity is decoded as4.81 with its original text retained, without a compatibility warning or a separate register profile.

Monitor and Diagnostics show the detected model/series and firmware. Diagnostic snapshots and structured identification logs include firmware and original identity text. Stable identity comparisons use family/model/serial and the scoped endpoint, rather than firmware text. Unlabeled trailing unit identifiers in older headers are also preserved for matching, without inventing a displayed serial number. Model, serial or endpoint changes still invalidate control scope.

## Internal differences retained

| Functional profile | Series definitions | Important retained differences |
| --- | --- | --- |
| LEL | 670,700 |670 temperature0.24426 versus7000.2442; distinct gauges/status/relay/service meanings;670 lock bits in60 versus700 LOCK STATE27 and LOCK SETTING60;670 latch mask17 versus700 Boolean settings72–74; assembly-specific span limits;700 ASCII identification page removed and numeric TYPE62/VERSION40/SERIAL63/YEAR65 used. |
| BTU | 690 |Reading0.0390625; low/high alarm meanings and own units; vacuum/pressure conversions; unspecified adjustment bounds remain read-only. |
| FID | 650 |Reading0.0000390625×FULLSCLE; PPM/MG context; SPAN VDC and voltage conversion; unit/page and writable-range uncertainties remain explicit. |

The documented670 D/K200%LFL conversion0.0078125 now follows the actual configured FULLSCLE200 range; FULLSCLE100 uses0.00390625, independent of firmware. Missing D/K range context is unverified rather than guessed. Manual gauge display overrides do not change conversion. Stored historical engineering values are not recalculated.

The observed670 fault sentinel/LCD handling applies to actual670 fault data, without selecting a firmware subset. Existing display-only retention and genuine communication-loss behavior are preserved. Bus pacing, addressing, retry/backoff limits and serialized ownership remain in the existing engine.

## Service and physical controls

The same Service editor reads the selected series definitions for CAL TIME, span temperature/voltage, alarm thresholds, latches and FAILSAFE. Existing Administrator-only setting changes and Operator/Administrator operating-command permissions are preserved. Every permitted change retains confirmation, matching identity, locks, busy/pending checks, limits/order checks, verified readback, audit and no ambiguous retries.

Known670 assemblies retain their existing scoped physical controls/settings for every firmware revision.700/690/650 physical writes remain unvalidated and disabled. Manufacturer-prohibited/internal/Cold Start/broadcast/generic writes remain unavailable.700 Modbus Lock/Unlock commands have no effect under Rev D and Save Settings permits factory changes, so those commands remain excluded. FAILSAFE stays read-only where prohibited or unverified; missing BTU/FID adjustment bounds do not become writable because a firmware gate was removed.

## Saved settings and recordings

Old selections LEL670Series/LEL700Series normalize to LEL, with the former simulation generation preserved. The old fta_4x key is accepted for migration and normalized to670; no separate legacy runtime profile remains. Instrument ID, name/model, connection/addressing settings, ranges, logging preferences and per-series recording selections are preserved. Selecting a family does not replace a saved physical instrument with a generic model. Both670 and700 simulation choices remain available.

Recording keys retain their existing per-series names, so saved recording parameter preferences and historical SQLite sessions remain readable. No database schema or historical data migration is required.

## Validation

See PROGRESS.md and VERIFICATION.md for this change's automated evidence. All automated transports are simulated or fake SDK clients; no real command or setting write is issued during development/testing. Hardware validation beyond the existing scoped670 evidence remains pending.
