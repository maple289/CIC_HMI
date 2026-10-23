# Manufacturer ambiguities and hardware-validation gates

All physical-device compatibility remains PENDING. No physical instruments have been accessed.

| ID | Evidence / question | Current behavior and required verification |
| --- | --- | --- |
| A1 | LEL PDF p5/printed89 and BTU p5/printed73: packet address = displayed ADDRESS minus1, including displayed1 -> packet0. | No packet0 is allowed, including reads. No broadcast. Record displayed and packet addresses separately. Read-only authorized bench test must determine direct vs minus-one behavior using nonzero candidates. |
| A2 | Page tables pair page00 0000H with registers1..64; page01 0100H with registers257..272. | PDU offset -1 is a simulation convention, not verified hardware truth. Physical read adapter requires an explicit offset (-1 or0), identified as unverified until bench testing. Never infer offset from successful zero-valued reads. |
| A3 | FID extract covers printed37..41 only. No serial protocol, page map, maximum read length, or poll limits. | Simulator uses the project's assumed RTU protocol; physical FID adapter is blocked. Obtain full serial section before allowing FID physical reads or writes. No alternate FID pages inferred from LEL/BTU. |
| A4 | FID UNITS row (PDFp3/printed39) has no register number or writable symbol. | Do not assign a guessed address. Units are explicit verified context; simulator labels its assumption. PPM and MG conversions supported, actual unit detection pending. |
| A5 | BTU measurement unit unspecified; status Downscale says -10%LFL despite BTU measurement. FID has the same questionable %LFL phrase. | BTU default label is 'unit unverified'. Status3 displayed as Downscale; do not infer threshold/unit. Validate with manufacturer. |
| A6 | BTU vacuum factor0.351734 (PDFp2/70) differs by10 from FID0.0351734 (p5/41). BTU vacuum typically40, FID setpoint negative. | Preserve exact published factors and sign; do not correct to a guessed factor. BTU vacuum writes blocked, FID vacuum writes blocked pending verified unit-dependent limits and behavior. |
| A7 | BTU ASP pressure0.105862 PSIG vs FID0.105882 psi and0.729412 kPa. | Keep independent factors. Unit-specific validation pending. |
| A8 | BTU alarm and calibration bounds blank; FID many writable-register ranges omitted. | No writes with incomplete range. Register metadata records manufacturer RW separately from HMI permission. |
| A9 | FID RLY TEST and MA TEST marked writable; LEL/BTU explicitly prohibit Modbus writes. | All test-output register writes blocked in initial release. No generic bypass. |
| A10 | FID FAILSAFE writable symbol; LEL/BTU explicit Modbus prohibition. | FAILSAFE read-only across initial release. Physical factory calibration registers also read-only. |
| A11 | CONTROL1/2 assign COMMANDS, FID says except9,10 while command words use0x0900 etc. | Do not guess low-byte vs high-byte encoding. Input remapping disabled. |
| A12 | Copy registers43/50 conversion not independently tabulated. DISPLAY51..55 unspecified ASCII field layout. | Copies use source conversion based on explicit copy description; label OUTPUT READING distinctly. ASCII exposed without invented field positions. |
| A13 | LEL old dilution D/K with version<=5.08 uses0.0078125, full scale200, MA SCALE may100/200. | LEL process conversion requires assembly and version; test both5.08 and5.09. Confirm hardware ID before physical engineering display. |
| A14 | LEL SPEED off0 only K types. TYPE table does not separately list all P suffix combinations in temperature table. | Initial generic simulation writes allow SPEED1..3 only; off remains blocked. Base-model temp/flow bounds applied by explicit model prefix. |
| A15 | LEL/BTU reply cap8/s at9600 and16/s at19200; other baud rates unlisted. | Conservative linear scaling for lower baud rates; cap16. Entire bus including failed requests is paced. Verify lower-rate capacity and real bus utilization. |
| A16 | Commands clear immediately; write acknowledgment does not prove execution. Reset/ack/save/lock may have no distinct STATUS transition. | No automatic physical commands. Simulator models deterministic transitions only. Real command outcome rules need recorded bench evidence, timeouts, lock behavior, and manufacturer confirmation. Never repeat ambiguous state-changing writes. |
| A17 | Source FID name in request was Menu_registers.pdf; repository uses FID_Menu_registers.pdf. | Existing PDF preserved and cited under actual name. Docs capitalization retained (Windows filesystem). |

## Future authorized read-only bench procedure

Record analyzer family, assembly, software, displayed address and serial settings before connecting. Use one instrument initially, obtain permission to open the named COM port, read only nonzero packet-address candidates, and record raw TX/RX. Establish register PDU offset using multiple identifiable values, not only STATUS0. Validate byte order, identification lengths, signed values, engineering unit selection and register-page limits. Repeat by supported family/version. No calibration, output testing, setting changes, or command writes are part of this procedure. A simulator is not evidence for any hardware gate.
