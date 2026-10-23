# PREVEX register specification

## Authority and scope

**700-series update:** `H7FTA700_RevD_PrevEx_instruction_manual.pdf` is authoritative for LEL700-series models and the reviewed7.xx firmware. Its independent inventory is included in REGISTER_TABLES.md. See LEL_700_REVIEW.md for menus and revised conversions, numeric identification, lock state, relay/service bits and command restrictions. The legacy LEL protocol/page/conversion descriptions below apply to the older extract only; they must not be carried into700-series handling automatically.

The authoritative sources are `LEL Menu registers.pdf` (7 PDF pages, printed85..91), `BTU menu registers.pdf` (7 pages, printed69..75, H7SNR690 Rev C) and `FID_Menu_registers.pdf` (5 pages, printed37..41), all in this folder. Page-separated extracted text is retained in `extracted/`. The inventory in REGISTER_TABLES.md records every numbered register shown in those extracts, including internal/prohibited entries excluded from polling. Gaps are unsupported, not zero-valued supported registers. FID UNITS and LEL/BTU menu VERSION have no separate numbered register; identification blocks carry VERSION.

## Protocol and pages

LEL/BTU: RTU, half-duplex RS485,8N1, default9600, supported300/600/1200/2400/4800/9600/19200. FC03 up to127 words, FC06 one word, FC16 exactly one word. Initial physical adapter implements READS ONLY, is not reachable from the GUI, and requires explicit authorization. Manufacturer broadcast support is deliberately excluded.

| Page | Documented logical registers | Wire-byte order | Applies to |
| --- | --- | --- | --- |
| 00 | 1..64 | high byte first | LEL/BTU |
| 01 | 257..272 | high byte first | LEL/BTU |
| 04 | 1025..1040 = copies257..272 | low byte first | LEL/BTU |
| 05 | 1281..1344 = copies1..64 | low byte first | LEL/BTU |

Reject crossing any supported window and reject unsupported/internal registers even within a page. Group contiguous safe documented registers only. Alternate pages apply a single per-word byte reversal before signed interpretation; never reverse a multiword string wholesale. FID pages/protocol are missing: simulation uses1..64 and257..288 as a software assumption; physical FID transport is blocked. PDU index mapping is explicit and unverified, see VERIFICATION A2.

8 replies/s total at9600,16 at19200; initial conservative rate scales linearly below9600. Timeout0.5s, library retries0. One scheduler owns a bus. Each failed job backs off (bounded) while healthy devices continue. No immediate retry loops. Manufacturer response delay5 characters minimum, up to250ms at max rate; rate limiter also respects3.5-character interframe time. Invalid start/page/CRC/oversize reads can be silently ignored; unsupported registers can return0. Out-of-range writes can receive an acknowledgment while data is ignored. No zero result is treated as proof of support.

## Conversion rules

All registers listed in the conversion tables are signed16-bit two's-complement. Exact decimal factors are retained. Other enum/bitfield/raw words are unsigned; unknown encodings are not invented. Inverse conversions round to the closest representable word, half away from zero. Ordinary simulated configuration writes require documented safe access and complete bounds, followed by readback. Physical writes remain unavailable.

| Format | LEL | BTU | FID |
| --- | --- | --- | --- |
| reading | raw*0.00390625 %LFL; D/K<=5.08 raw*0.0078125 | raw*0.0390625; unit unverified | raw*0.0000390625*FULLSCLE; US=PPM / metric=MG |
| temperature | raw*0.24426 degC | raw*0.24426 degC | raw*0.24426 degC |
| flow | raw*0.00172936 SL/min | not documented | not documented |
| voltage | not documented | not documented | raw*0.0024426 VDC |
| current | raw*0.000625+4 mA | same | same |
| current trim | raw*0.1 mA | same | same |
| vacuum | not documented | raw*0.351734 inH2O (verify) | raw*0.0351734 inH2O or raw*0.00879336 kPa |
| aspirator pressure | not documented | raw*0.105862 PSIG | raw*0.105882 psi or raw*0.729412 kPa |

MA TEST/CAL/FAULT are also listed in reading format by all manuals. The metadata uses their documented mA view; they are not substituted for process measurements. FID reading display has1 decimal for FULLSCLE<=100, otherwise0; GUI applies this precision. Other display precision is an HMI presentation choice rather than a manufacturer claim. Metadata source pages for the conversion table are LEL PDF2/86, BTU PDF2/70, FID PDF5/41.

## Commands (register8)

0x0000 inactive;0x0100 acknowledge;0x0200 reset;0x0300 zero calibration;0x0400 span calibration;0x0500 full calibration;0x0600 zero test;0x0700 span test;0x0800 full test;0x0900 save;0x0F00 software calibration lock;0x1000 unlock. These candidate commands are documented for all three families. The initial physical transport has no command path.

0x0A00 Cold Start is prohibited. LEL/BTU0x0B00 menu,0x0C00 select,0x0D00 flashlight emulation are excluded from normal controls;0x0E00 momentary lock is internal and prohibited. These four are absent from the supplied FID command list and must not be inferred there. Never automatically repeat an ambiguous command timeout. Success requires status/outcome evidence, not rereading register8. Save may not change STATUS. LEL/BTU EEPROM writes occur60s after the last configuration write; Save All forces immediate persistence. FID extract does not document that delay.

## Status, relays, service, locks

STATUS enum tables appear in REGISTER_TABLES.md for each family. Unknown codes remain visibly unknown. BTU1/2 are low/high alarms, LEL/FID1/2 warning/danger. LEL20/21 flow low/high; BTU/FID16/17 vacuum low/high. Fault Downscale wording includes questionable %LFL in BTU/FID; do not infer the physical threshold.

RELAYS bits7..0 = T,I,S,Z,H,F,D,W: heater,ignition,span valve,zero valve,horn,fault,danger/high,warning/low. SERVICE59 LEL/BTU bits7=AIR_FUEL,6=reserved0,5=CHK_RDNG,4=CHK_DATA,3=CHK_LED,2=CHK_SPAN,1=CHK_ZERO,0=CHK_FLOW (LEL) or N/A (BTU). FID SERVICE is unsupported. CAL LOCK60 bit0 hardware and bit1 software, read-only. These indicate instrument state, not a substitute for hardware interlocks.

## LEL assembly TYPE62

0 undefined (DATA LOST),1 SNR671,2 SNR671D,3 SNR672P,4 SNR672,5 SNR672D,6 SNR672K,7 SNR674P,8 SNR674PL,9 SNR674,10 SNR674D,11 SNR675,12 SNR675D,13 SNR675K. D air dilution; P0.6%volume propane calibration option; K dilution with SPEED off; L low-flow adjustment option (now standard). Factory TYPE/SERIAL and calibration trims remain read-only.

## Access and ambiguity policy

Inventory access labels distinguish R, RW manufacturer writable, R-panel (panel writes only; no Modbus), and command. Actual physical permissions remain read-only for every user. Initial simulated configuration validation covers only entries marked validated with complete bounds/choices. Metadata records minimum/maximum, units, signedness, required role, category, restrictions and source. Unknown/default fields are not manufactured. VERIFICATION.md is the open-question register and hardware gate list.
