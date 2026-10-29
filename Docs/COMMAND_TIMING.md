# ACKNOWLEDGE / RESET timing investigation — 2026-10-28

## Cause and correction

Previously `PendingEffect` occupied the same `pending` field as calibration and lock verification. Every ACK/RESET therefore disabled the command group until a conclusive effect or an 8–30 second verification deadline. A persistent fault or an already Normal instrument commonly produces no observable clearing effect. This was the source of the several-second post-reply lock, not an automatic write retry. Feedback could also briefly re-enable buttons before the next pending snapshot. The LED's three-second timer was independent but did not release that lock.

Manufacturer basis: 670 Rev Q section 12.2, printed page 87 (PDF page 91), says the host should verify COMMANDS by reading STATUS, because COMMANDS clears when executed and usually reads zero. This applies to both ACK and RESET. It does not prescribe an eight-second UI lock or demand a STATUS transition. Sections 8.2/8.3, printed pages 59/60, describe horn/service acknowledgment and conditional clearing of latched alarms. Persistent faults and CHK RDNG can remain; RESET can reactivate an uncorrected alarm or initiate ignition. The normal poll supplies the subsequent STATUS read; the bounded relay/service correlation is additional HMI evidence, never proof from an unchanged or later Normal STATUS alone.

The controller now separates the serialized transmission, a 500 ms shared anti-repeat cooldown, background ACK/RESET effect observation, and longer safety interlocks. Commands/adjustments take priority over queued history/inspection and the next polling transaction; an active transaction and manufacturer bus pacing are never interrupted. Existing fresh identity, role, confirmation, status and applicable lock checks remain. Required preflight reads explain much of the pre-transmission delay; they were not removed. Redundant synchronous ACK/RESET post-write reads and the bench path's 250 ms sleep were removed. Effects use the existing normal polling cache, including its acquisition ages. New confirmed actions end an older observer without attributing later changes to the old action.

Calibration/lock pending states and ambiguous delivery still block unsafe actions. Timeout, invalid echo or communication loss never trigger an automatic resend. Safe rejection releases the temporary UI state; uncertain delivery remains explicitly interlocked. The LED is deduplicated by receipt ID, so an older worker receipt cannot replay it when a different command starts. Queued UI actions remain locked until their own receipt arrives.

## Controlled before/after comparison

Same simulator, 9600 baud, 250 ms polling, unchanged valid STATUS/RELAYS, automatic confirmation in the isolated test only. Times below are milliseconds after the simulated click. The baseline was measured at commit `7a92b5a`; final values are from `tmp/command-timing-final.json`. Earlier baseline evidence is `tmp/command-timing-before.json`. Windows scheduling introduces small variation; these are observations, not deadlines.

| Stage | ACK before | ACK after | RESET before | RESET after |
|---|---:|---:|---:|---:|
| Queued | 16 | 15 | 0 | 0 |
| TX / valid reply (instant simulator echo) | 454 | 437 | 344 | 422 |
| LED activation | 625 | 437 | 500 | 422 |
| Effect verification starts | 563 | 469 | 438 | 562 |
| Stable command-button release | 8750 | 1015 | 8735 | 1062 |
| Effect verification ends | 8719 | 8578 | 8641 | 8562 |

The old UI briefly released at 563/438 ms and re-locked at 625/500 ms; the table uses the stable release. After the correction the buttons recover roughly 0.6 seconds after the simulated response even while verification remains active. `scripts/measure_command_timing.py` reproduces this safely with simulation only.

## Authorized live evidence

The user explicitly authorized live commands and manually signed in. Only ACK/RESET were exercised through the application's target-confirmation flow; no calibration, configuration, broadcast or generic register write was issued by the agent. Target: COM4 / 9600 / address 1, detected SNR671 firmware 4.81. Its 5.12 command-map use remains a user-approved assumption; these timing observations do not validate the whole firmware map.

Old packaged build: RESET was confirmed at 21:28:11.090 UTC; the sampled UI first showed its acknowledgment LED at 21:28:12.623 and enabled buttons at 21:28:13.630. The effect was observed, so this particular baseline ended early rather than waiting eight seconds. Sampling was approximately 300 ms plus capture overhead. The old build lacked stage instrumentation, so exact historical queue/TX/RX times cannot be claimed. The earlier baseline ACK was acknowledged but unverified; its UI sampling started too late to establish exact release time.

New packaged build, monotonic stage log; offsets below start at confirmation acceptance, excluding human confirmation dwell:

| Stage (ms) | Agent ACK | Agent RESET | Additional operator-confirmed RESET observed in log |
|---|---:|---:|---:|
| Confirmation UTC | 21:32:49.447 | 21:33:10.177 | 21:33:36.278 |
| Queued | 4 | 9 | 8 |
| Dequeued | 19 | 13 | 14 |
| TX started | 1324 | 675 | 692 |
| Valid response | 1368 | 711 | 727 |
| LED activated | 1369 | 712 | 728 |
| Verification started | 1371 | 714 | 730 |
| Global/UI temporary lock released | 1872 | 1213 | 1233 |
| ACK/RESET buttons enabled | 1873 / 1874 | 1214 / 1214 | approximately 1234 |
| Verification completed | 3649 | 1333 | 8740 |
| Outcome | Effect observed | Effect observed | Acknowledged, NOT_VERIFIED |

The write response itself took about 44 ms for ACK and 36 ms for RESET. Queue wait was 15/4 ms; the remaining pre-TX time was fresh safety reads and serialized pacing. Buttons returned about **505 ms / 503 ms after the valid reply**, before the independent LED expired. The additional operator-confirmed RESET also released after about 506 ms although its no-effect observation continued for eight seconds. This directly covers the persistent/no-visible-effect case without treating a later Normal STATUS as proof. The two agent requests each produced one TX. Raw bounded evidence is in `tmp/live-command-after.json`; the application log is `command-timing.jsonl` in its data folder.

The live trace exposed replay of the previous ACK LED during RESET dequeue. The final UI deduplication/queued-receipt regression addresses this separately; it does not change transport timing. Live timings were captured before that final display-only correction. Simulator regressions and packaged smoke validate the final build without additional live writes.

## Diagnostics and verification

`command-timing.jsonl` records UTC and monotonic timestamps with request ID and code: button click, confirmation, queue/dequeue, transport/TX, wire response, validated response/error/timeout, LED, verification start/end, transaction finish, temporary lock release and individual button transitions. It rotates at about 2 MB with one previous file, retains at most 4096 in-memory events, omits credentials/session tokens, and tolerates logging failures. Transaction locking/pacing and the SQL command audit remain authoritative safety mechanisms.

Simulator matrix: ACK and RESET under Normal, resettable alarm, persistent fault, delayed response, lost acknowledgment after one write, communication loss and repeated clicks. Queue priority/FIFO is checked separately; existing bus concurrency/pacing tests preserve serialization. Existing fake physical tests cover calibration/lock interlocks, identity/firmware restrictions, roles and confirmation. Additional regressions cover superseded observers and stale receipt/LED handling. See PROGRESS.md for final counts and packaged evidence.
