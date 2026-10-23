# LEL 700-series full-manual review

Source: `H7FTA700_RevD_PrevEx_instruction_manual.pdf`, H7FTA700 Rev D, August 2025. The PDF has 143 pages; core manual printed page numbers match PDF pages. Reviewed menus61–68, service90, serial115–127 and revision128–130. Serial tables119/127 were rendered and checked. Complete searchable extraction is in `extracted/`. This is the primary LEL 700-series reference. The older LEL extract remains the reference for older assemblies/firmware.

## Distinctions that affect implementation

| Area | Rev D evidence | Implemented behavior |
| --- | --- | --- |
| Identification | p125 TYPE62 adds16–23 for SNR701/702/704/705 and D variants; VERSION40 is numeric; SERIAL63 and YEAR65 identify the unit. p127 removes ASCII257+ (blanks). | Try legacy FC03 identification first. Only on blank/failed legacy identification and recognized700 TYPE, read40/63/65 separately and validate firmware/year/serial. Never use40 as a version register on legacy units. |
| GAUGES | p61/64/119 list peaks38/39, BLOCK TEMP9, BLOCK SETTING24, SAMPLE FLOW15, FLAME TEMP11, ZERO FLAME TEMP29, SPAN FLAME TEMP30. | Dedicated700 readouts include these plus primary reading1/status2. Flow thresholds23/42 and output50 belong to other menus, not the700 Gauge menu. |
| Conversions | p116 specifies temperature0.2442 (older extract0.24426), flow0.00172936, %LFL0.00390625, bar0.0001, hPa/kPa0.01, version0.01, seconds0.1, percent0.01; engineering values signed16-bit. | Independent700 inventory and exact factors. Do not change older profiles to the new temperature factor. |
| Main scale | p127 FULL SCALE3 and analog scale57 always100. | Prefer live3; retain optional manual display range. Manual display changes do not modify the instrument. |
| STATUS | p117 code15=12VDC Fail,16/17=Dilution Low/High,22/23=Fuel Pressure Low/High,24=TC1 Fail; both Danger and Danger Flooded use2. | Separate enum mapping; code2 cannot distinguish those two conditions. Do not invent a second simultaneous STATUS bit. |
| RELAYS | p127 format00000AKC TISZ0FDW; Horn no longer supported. A=air/fuel cutoff(bit10), K=service(bit9), C=calibrating(bit8). | Expanded700 indicators; omit obsolete Horn. |
| SERVICE | p126 bits0/1/2/4/5,8–14 are defined;3/6/7/15 unused. | Decode the documented12 individual checks; omit obsolete LED and AIR_FUEL service-bit labels. |
| Locks | p126 LOCK SETTING60 replaces old calibration-lock flags; LOCK STATE27 is0 unlocked,1 cal/tests,2 settings,3 all. | Calibration/test preflight checks actual LOCK STATE27 bit0. LOCK SETTING remains read-only in this preview. |
| Commands | p118 Lock0F00/Unlock1000 no longer affect Modbus; Save0900 allows factory settings changes. | Disable these for700. ACK0100, RESET0200, CAL0300–0500 and TEST0600–0800 remain confirmed, audited simulator controls. |
| Additional commands | p118 documents Zero Adjust0E00, Check Utilities1100 and relay/gas alarm tests1200–1700. | Recorded in this review but excluded from the initial approved operational allowlist. They alter calibration or hardware outputs; no generic bypass. Cold Start0A00 and remote/internal controls remain prohibited. |
| Serial | p115 supports9600–38400, standard19200,8N1, FC03 max127, FC06/16(single word); unsupported registers return2020H. | New default simulation is700 at19200. Existing conservative engine remains capped19200;38400 is not offered pending timing validation. Older configured rates remain available for legacy instruments. |

## Complete menu coverage in the inventory

`profiles/lel700.py` records all numbered entries in the full serial tables, including flow system, optional dilution/fuel/purge monitors, calibration, alarms, alarm tests, analog outputs, controls, COM port, settings, security, register diagnostics and legacy compatibility outputs. Generated `REGISTER_TABLES.md` includes an independent700 section. Factory settings, undocumented limits and optional-hardware writes remain blocked. Only the Gauge menu and approved command subset are exposed operationally; other menus are references for subsequent configuration work.

## Unresolved items

- p127 says register106 is the highest register and that none above105 are valid, while p125 assigns TC TIME CONST106. Inventory records106 but blocks polling/inspection.
- p115 forbids crossing page boundaries but supplies no page/alternate-byte-order map. Reuse no legacy aliases. Reads above64 are single-word simulation reads; physical700 access is blocked until its page map/addressing/timing are verified.
- p117 STATUS header says upper23 while its list extends27. Preserve explicit list and record contradiction.
- p122 alarm-test heading says one hour; individual descriptions say15 minutes. These tests are not exposed.
- p123 describes26/32/44 in %LFL while p116 also lists a tenths-mA lookup format without assigning registers. Reading-format interpretation follows the explicit register descriptions; writes are blocked pending confirmation. p123 register25 bounds also mix %LFL and mA.
- p63 says minimum speed refers to register50, whereas p121 defines SPEED20 and p125 MINIMUM SPEED100. Do not infer a write to50.
- Several p120 pressure defaults/ranges mix bar and kPa or provide zero/zero bounds. Preserve stated engineering-unit conversions, flag contradictory limits and block editing.

No physical analyzer was accessed. Simulation evidence does not establish firmware or electrical compatibility.
