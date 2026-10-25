# Normal serial-port connections

Read-only use of all available serial ports is authorized. Select Hardware, choose an enumerated COM port and connection settings, and press **Connect** or **Test Connection**. No additional authorization prompt, session grant or special launcher is required for ordinary monitoring. A saved hardware connection can resume on startup when its selected port is available. The application opens only that selected port, not every detected port. Removed/unavailable ports remain blocked until an available port is selected.

Normal physical connections use the read-only transport and never acquire command permission from port settings or identity. Test Connection always uses a read-only transport, even within a bench session. Moving a bench session to another endpoint drops its special command permission. Register-page restrictions and unresolved profile/protocol definitions still apply independently of port access.

For a positively identified, documented LEL670 firmware5.12-5.x instrument, the operating buttons become available after Operator/Administrator sign-in. Each command requires target confirmation and fresh identity/status/lock checks. A scoped fixed-register8 command transport is activated only for a confirmed command; normal connection startup remains read-only. SAVE ALL requires Administrator and warns about EEPROM persistence. Hardware/calibration locks, busy/pending conditions and unsupported manufacturer commands remain enforced. Recognized670 firmware4.81 uses the same operating set by explicit user instruction, with compatibility identified as an assumption; see COMMAND_READINESS.md.

The user has specifically permitted calibration/test commands while an analyzer fault is active. A known fault alone does not disable those buttons; confirmation identifies the current fault. Firmware, controller locks, busy/pending and valid-response checks remain. An unchanged pre-existing fault after acknowledgment produces WAITING_STATUS, not a fabricated execution result. The HMI waits for a fresh sequence and reports UNKNOWN if confirmation times out; it never retries automatically.

# Authorized SNR671 controller bench operation

For the previously authorized legacy LEL controller, open the application normally and click **Connect SNR671 / COM4**. This starts the scoped bench session from the interface; special launch flags are optional. The alternatives remain `scripts/launch_controller_bench.cmd` or the executable with `--controller-com4-bench`. Only the tested COM4/9600/packet1/PDU-1 endpoint is opened. Sign in/create a local Administrator to enable all eleven documented operating commands; each action requires confirmation and current controller checks. The result card distinguishes a reply from observed state changes or an unknown outcome. Calibration/test/save/lock commands are available under the user-approved5.12 map for4.81. Generic configuration writes remain blocked. Close any prior bench instance first so only one owner uses COM4. Use `launch_controller_readonly.cmd` for monitoring without commands. For the observed older FTA8001H fault state, the primary gauge mirrors the fresh controller LCD(-99%LFL). Brief nonnumeric intervals retain the last numeric gauge value for at most four seconds from its actual sample time. Retention is display-only, visibly stale and independent of the connection indicator. Raw register1 remains in Diagnostics. See SNR671_BENCH.md for evidence and limitations.

The bench button prepares the known endpoint and its identity scope in memory and requires fresh matching identification. It does not save a command authorization flag or execute any command during connection. Normal monitoring on any available port uses Connect/Test Connection and needs no bench grant.

The following general preview instructions describe simulation and monitoring; the documented670 and user-approved4.81 controls follow the restrictions above.

# Operating the single-analyzer preview

Start `scripts/launch_windows.cmd`, or run `.venv/Scripts/python.exe scripts/run_hmi.py`. PowerShell activation is optional. A new installation opens one simulated700-series LEL analyzer with Auto Detect selected. The amber simulation banner remains visible. Synthetic data must never be used for safety functions.

## Choose and connect

**Choose Analyzer Type** offers Auto Detect(default), LEL, BTU and FID. Manual type selection also selects the matching simulated instrument; Auto Detect offers a separate simulated-family choice. Only fields applicable to the selected family are shown. For LEL, choose700 or legacy simulation. Click OK to confirm the choice, stop the old session, clear old readings and start one new connection. Cancel preserves the previous settings. Existing multi-device settings migrate to one selected instrument; the original is backed up as `settings.v1-backup.json`.

COM port, baud, timeout, nonzero address, address compatibility and register offset are saved. Minus-one addressing requires a displayed address of at least2; the dialog shows the resulting nonzero packet address. Hardware monitoring connects read-only on the selected available port without another authorization step. Supported documented670 operating writes require sign-in, per-command confirmation and fresh checks. Firmware4.81 uses the same operating set by user instruction, with a visible unverified-compatibility note.

**Test Connection** stops monitoring, performs identification and a read-only response check, then reports family/model/version/serial without enabling controls. Choose Connect to start polling. Unknown identity permits an explicit manual profile but keeps commands disabled. A mismatch uses the detected family's definitions and displays a warning; choose the matching type or Auto Detect to resolve it.

The separate **Test Connection result** window shows a green passed result, a red failed result with its error, or an amber communication-established/identity-unresolved result. It includes mode, COM port, baud/serial settings, configured address, selected/detected profile, model, firmware, serial availability and genuine compatibility notes. It opens after the worker closes the serial port. The main screen explicitly says monitoring is stopped after this one-time check; unavailable live readings do not mean the test failed. Close the result with OK and click **Connect** for continuous monitoring.

Raw nonstandard firmware text is retained beside its provisional interpretation. Compatibility warnings describe the specific undocumented behavior; Administrator sign-in does not change detection or dismiss limitations. Supported successful identification clears prior warnings. Test Connection never activates operating controls or sends an operating command.

Digital measurement/status cards use a consistent230px width, approximately two-thirds of the previous normal-window width. They reflow according to available space rather than stretching across three columns. Labels/values wrap when necessary; compact internal margins retain the previous normal card height. The shared layout applies to670/700/BTU/FID and grows rows only when text requires it.

LEL700 numeric identification replaces the removed legacy ASCII page. See LEL_700_REVIEW.md. FID units remain explicit context because its supplied UNITS entry lacks an address. BTU units remain labeled unverified.

## Gauge and indicators

The circular gauge shows a blue negative section, a bold zero marker, the positive full scale and instrument alarm bands. For LEL, the negative endpoint is-30 normally and-100 while current STATUS or Fault relay indicates a fault; it returns automatically when the fault clears. FULLSCLE3 supplies the positive range when available. Optional manual fallback or display override is in Choose Analyzer Type. It changes only the display, never the instrument or FID conversion. Values beyond either endpoint retain their actual numeric reading. Negative sign alone does not determine a fault; STATUS does.

All documented Gauge-menu parameters for the selected revision appear as digital readouts with names, units, register numbers and validity. Scroll for additional tiles and the live plot. BTU's unnamed42 is marked unavailable and never polled. Unsupported registers are not invented. Missing/stale/offline measurements show `--`.

The top panel shows one current STATUS enum and separate relay/service bits. Only current active indicators are shown; inactive indicators and empty rows are hidden. Horizontal scrolling remains available when many indicators are active. Communication quality remains visible, and stale/unavailable indicators are hidden.700-series LEL has different relay/service labels from legacy LEL. FID SERVICE is unsupported by the supplied documentation. Text accompanies colors.

## Commands and local accounts

Guest/Viewer is the initial role; controls remain disabled. Use **Sign in / create account** to create the first local Administrator with a password of at least12 characters. There is no default password. Sign out through the same button. Passwords use salted PBKDF2 hashes. The account store supports Viewer, Operator and Administrator; creating additional users is an Administrator-only API operation, with a management UI remaining future work.

Operator/Administrator sessions may run approved simulator commands and documented6705.12-5.x operating commands. SAVE ALL on hardware requires Administrator. Each action requires target confirmation, a current connection, fresh matching identification and applicable calibration-lock/status checks. Pending or unknown outcomes block duplicates. Commands are sent once, audited and evaluated using STATUS; pre-command cached STATUS samples are ignored. Ambiguous timeouts are never retried; reconnect and review state. A write acknowledgment is not proof of execution. Ack/reset/save may report sent/unverified because no unique success signature is documented.

For700 LEL, Save Settings and Modbus Lock/Unlock are unavailable under the revised manual. Calibration/tests use LOCK STATE27. Cold Start, internal commands, relay/gas tests, Zero Adjust and generic write bypasses are unavailable. Factory configuration is read-only. Measurement logging can be toggled in Choose Analyzer Type; events and command audit continue independently.

## Other pages

- Live trends: signed values, mouse-wheel zoom, drag pan; bounded1800 points. Communication gaps break the curve.
- History / CSV: select time range, load up to5000 primary records, export those rows with instrument ID and UTC timestamps. Plots display local time.
- Alarm history: latest500 status/communication transitions, independent of measurement logging.
- Diagnostics: poll/error counts, response timing, bounded TX/RX data, documented read-only inspection. Traffic columns have stable widths; drag header dividers to resize them and use horizontal scrolling for long hexadecimal frames. Inject simulated timeout/CRC/protocol/unknown-identity/lost-command-ack faults. Set fault to `none` for recovery; backoff can take up to60s. Forced readings and STATUS codes support offline testing.
- Command audit: user, target, command, outcome and detail, including rejections and unknown results.

## User data and deployment

Settings, simulation.sqlite3, users.sqlite3 and rotating application.log are stored in Qt's Windows AppLocalDataLocation (shown in the status bar), normally `%LOCALAPPDATA%/CIC/PREVEX HMI`. Normal operation needs no Internet, subscription or AI service. Settings save atomically; malformed files are preserved. Measurements retain90 days, events/audits independently. Raw traffic holds500 frames, latest100 displayed. Application logs rotate at2MB with3 backups.

Build on Windows Python3.12 x64 using requirements-lock.txt:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe scripts\run_hmi.py --smoke-test --data-dir tmp\monitoring-smoke
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm build_windows.spec
```

Launch `dist/PREVEX-HMI/PREVEX-HMI.exe`; distribute the entire folder, including `_internal`. The build is unsigned. Installer/signing, clean Windows10/11 testing, advanced retention/archival, user-management UI and hardware validation remain release work. No simulator test establishes physical compatibility; see VERIFICATION.md.
