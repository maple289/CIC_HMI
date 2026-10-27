# Independent Trend window and recordings

Use **Open Trend** on the main toolbar. The Trend is a separate, non-modal Windows window with its own minimize, maximize, resize and close controls. Open Trend raises the existing window. Move it to another connected monitor using its title bar. Position and size are saved in `trend-window.json` beside the application data files; a disconnected monitor's saved position is brought back onto an available screen. Closing Trend hides it without stopping polling or recording. Closing the main HMI closes Trend and ends the active session.

The main Gauge screen has no embedded graph. Live trends and History / CSV navigation retain launch pages for the independent window. Existing continuous-monitoring history and its displayed-data CSV export remain available in its **Legacy monitoring history** tab. Existing accounts, commands and physical write restrictions are unchanged.

## Recording controls

- **Manual** is the default. Start Recording starts a new session on the next current analyzer snapshot. Stop Recording ends it. Starting again creates a separate session.
- **Automatic** starts a new session when communication is established, pauses during loss/staleness and resumes that same session after recovery. Stop Recording disarms automatic recording until Start Recording is pressed or Automatic is selected again.
- Capture intervals are **1, 2, 5 or 10 seconds**, default1. The interval limits recording capture; it does not change Modbus polling. If the analyzer is polled every2 seconds, a1-second recording interval cannot create additional1-second measurements. Cached values already captured in the session are not written again.
- **Main measurement and status only** narrows the next session to registers1/2. Otherwise each profile's manufacturer GAUGES menu is selected, including the primary measurement and STATUS, peaks, temperatures, flow/vacuum and other applicable readings. Calibration-menu and alarm-setting cards added to the main HMI are not automatically added to GAUGES recording. Parameter names, units and conversions come from the existing670/700/BTU/FID profiles. BTU/FID hardware/units limitations still apply.
- Changing mode, interval or parameter selection ends an active session and starts a separate session with the new metadata. Manual recording ends on an analyzer identity/profile/endpoint/unit/full-scale change and requires Start Recording again. Automatic recording starts a separate session for the new stream.

The Trend shows state, elapsed session time (including pauses) and captured-frame count. Recording settings are saved in the existing settings file. The Manual preference does not automatically restart an old session after application restart. Automatic starts a new session after identification. An interrupted session remains queryable with an empty end time rather than an invented shutdown time.

## Timestamp and quality rules

Acquisition time is stamped on the polling worker when each register block returns. Recording consumes those cached snapshots on a separate thread, with no transport reference, reads or commands. Each value retains its response timestamp. Values originating from the legacy fault LCD use the actual LCD-response timestamp. The unique `(session, register, acquisition timestamp)` key prevents repeated cache samples from appearing as new acquisitions.

Frames are sparse: a parameter absent from a frame has no new observation at that capture. This is different from a new observation whose value is unavailable. No forward fill, interpolation, numeric clamp or held-gauge substitution enters recordings. Communication loss produces one gap frame without measurements; recovery produces a marker and the next fresh observations. STATUS has its own source timestamp, and communication quality and per-parameter quality are retained. Existing instrument faults remain visible and do not create healthy-quality data.

## Historical viewing and CSV

Open **Recorded sessions**, refresh the list, choose the session and parameter, then **View recording**. The plot retains signed values, engineering units, mouse-wheel zoom, drag pan and a prominent zero reference. Communication gaps break the line. The display is bounded to the first50,000 observations per session/parameter and says when this limit applies; CSV export is not bounded by the plot limit.

Export CSV offers:

1. Current recording session.
2. Selected previous session.
3. All recording sessions within a **capture-time UTC** range.

Choose a destination in the standard Windows Save dialog. The default name follows `PREVEX_LEL670_YYYY-MM-DD_HHMMSS.csv` (profile and local filename time vary). CSV uses UTF-8 BOM, comma separation, CRLF records and quoted fields. Headers identify parameter names and engineering units. Base columns include session, profile, model, firmware, analyzer identification, source, session start/end, interval, capture UTC, STATUS, STATUS acquisition UTC and communication quality. Each measurement has value, acquisition UTC and quality columns. Unavailable/unobserved fields are blank; negative numeric values remain signed numbers. Different profiles or units receive separate named columns, and each row retains its session and source metadata.

In Excel, if the local installation presents its Text Import Wizard, select **Delimited**, **UTF-8 /65001**, and **Comma**. No regional Windows or Excel settings need to be changed. Analyzer-supplied identity text is escaped when it could be interpreted as a spreadsheet formula.

Export streams read-only SQLite queries on a separate thread. It writes a temporary file beside the chosen destination and replaces the destination only after success. A failed export preserves an existing destination and does not stop polling or recording. Concurrent export sees a consistent snapshot of each selected session; observations arriving after that snapshot are available on a later export.

## Storage and failure behavior

Recording tables extend the existing `simulation.sqlite3` and `hardware.sqlite3` files. Sessions, captured frames and per-parameter observations are separate from legacy measurement-history retention. Existing90-day measurement cleanup does not delete recording sessions. There is no direct CSV writing during collection.

Recording storage errors, including full disk, stop/disarm recording and show an error; committed data remains available. Resolve storage and explicitly start again. There is no hidden retry or successful-recording claim after a storage failure. Legacy history storage failures also leave polling active, while audit-dependent commands fail closed until reconnect. SQLite lock waits in the monitoring and recording paths are bounded. Export errors appear in Trend. Application shutdown stops acquisition and closes the active recording; an unwriteable shutdown may leave its metadata marked unfinished.

No Modbus write is sent by any Trend, recording, historical-view or CSV operation. Simulator tests do not establish physical analyzer compatibility.
