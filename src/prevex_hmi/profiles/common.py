"""Independent per-family register inventories transcribed from the supplied PDFs.

Source page references are PDF page numbers followed by manufacturer printed pages.
RW describes manufacturer access, NOT physical write availability in this release.
"""
from dataclasses import replace

from prevex_hmi.registers.schema import Profile, Register

COMMANDS = {
    0x0100: "Acknowledge", 0x0200: "Reset alarms", 0x0300: "Zero calibration",
    0x0400: "Span calibration", 0x0500: "Full calibration", 0x0600: "Zero test",
    0x0700: "Span test", 0x0800: "Full test", 0x0900: "Save settings",
    0x0F00: "Calibration lock", 0x1000: "Calibration unlock",
}

BASE_STATUSES = {
    0: "Normal", 1: "Warning", 2: "Danger", 3: "Downscale",
    4: "Zero On", 5: "Span On", 6: "Purging", 7: "Calibration ending",
    8: "Zero calibration failed", 9: "Span failed: low", 10: "Span failed: high",
    11: "Warmup", 12: "RAM test", 13: "RAM failed", 14: "Data lost",
    15: "EEPROM failed", 18: "Temperature low", 19: "Temperature high",
    24: "A/D failed", 25: "TC2 failed", 26: "Flameout", 27: "ROM failed",
}


def make_profile(family: str) -> Profile:
    fid = family == "FID"
    lel = family == "LEL"
    base = "FID PDF" if fid else f"{family} PDF"
    pages = {
        "gauges": "2 (38)" if fid else "3 (87)" if lel else "3 (71)",
        "calibration": "3 (39)" if fid else "4 (88)" if lel else "4 (72)",
        "outputs": "3 (39)" if fid else "5 (89)" if lel else "5 (73)",
        "communication": "4 (40)" if fid else "5 (89)" if lel else "5 (73)",
        "alarms": "3 (39)" if fid else "6 (90)" if lel else "6 (74)",
        "diagnostics": "4 (40)" if fid else "7 (91)" if lel else "7 (75)",
        "conversion": "5 (41)" if fid else "2 (86)" if lel else "2 (70)",
    }
    regs: dict[int, Register] = {}

    def add(number: int, name: str, meaning: str, *, section: str = "diagnostics", **kwargs: object) -> None:
        regs[number] = Register(number, name, meaning, source=f"{base} p.{pages[section]}", **kwargs)

    def scaled(number: int, name: str, meaning: str, conversion: str, *, section: str = "gauges", **kwargs: object) -> None:
        add(number, name, meaning, conversion=conversion, signed=True, section=section, **kwargs)

    scaled(1, "READING", "Process measurement", "reading")
    add(2, "STATUS", "Operating status code", section="gauges")
    add(3, "FULLSCLE", "Maximum measurement at 20 mA" if fid else "Full-scale range; standard 100 LEL / 1000 BTU",
        section="alarms" if fid else "diagnostics", access="RW" if fid else "R",
        minimum="10" if fid else None, maximum="32000" if fid else None,
        write_policy="validated" if fid else "blocked", restrictions="Changing FID scale changes measurement interpretation" if fid else "Legacy LEL D/K <=5.08 has full scale 200")
    add(4, "RELAYS", "Logical active flags: bits 7..0 TISZ HFDW")
    for n, name in [(5, "LO ALARM" if family == "BTU" else "WARNING"), (6, "HI ALARM" if family == "BTU" else "DANGER")]:
        scaled(n, name, "Alarm threshold in reading format", "reading", section="alarms", category="Alarm Settings", access="RW",
               minimum=("5" if n == 5 else "10") if lel else None, maximum="60" if lel else None,
               write_policy="validated" if lel else "blocked", restrictions="WARNING must be below DANGER" if lel else "Range not documented; editing blocked")
    scaled(7, "CAL RDNG", "Span-calibration target", "reading", section="calibration", access="RW", category="Calibration",
           restrictions="LEL range 40..80, P type 25..80, default 60; BTU bounds blank; FID bounds absent. Calibration editing deferred")
    add(8, "COMMANDS", "Self-clearing command word; evaluate STATUS after execution", section="calibration", access="command",
        restrictions="Dedicated confirmed command path only; never generic configuration writes")
    for n, name, meaning in [(9, "HSG TEMP", "Flame-cell housing temperature"), (11, "FLAME", "TC1 flame temperature")]:
        scaled(n, name, meaning, "temperature", unit="degC")
    if lel:
        scaled(15, "FLOW", "Sample flow in standard liters/minute", "flow", unit="SL/min")
    else:
        scaled(10, "CELL VAC", "Flame-cell / sample vacuum", "fid_vacuum" if fid else "btu_vacuum", unit="inH2O",
               restrictions="BTU factor 0.351734 transcribed literally; verify magnitude and sign" if not fid else "Unit mode independently verified")
        scaled(33, "ASP PRES", "Aspirator / E-P pressure needed for vacuum", "fid_pressure" if fid else "btu_pressure", unit="PSIG", section="gauges")
    if fid:
        scaled(12, "RAW RDNG", "Hydrocarbon signal voltage", "voltage", unit="VDC")
    if family == "BTU":
        for n, name in [(13, "4 MA RDNG"), (14, "20 MA RDNG")]:
            scaled(n, name, "Measurement corresponding to analog-output endpoint", "reading", section="outputs", access="RW", restrictions="Range unspecified; editing blocked")
    add(16, "A/D REF", "A/D reference; expected raw 506 +/-25")
    add(17, "LATCHES", "Latched alarm flags; RELAYS layout", section="alarms", access="RW", restrictions="Allowed writable bit mask not specified; LEL default warning/danger/fault latching")
    add(18, "FAILSAFE", "Fail-safe flags; RELAYS layout", section="alarms", access="RW" if fid else "R-panel",
        restrictions="LEL/BTU explicitly prohibit Modbus writes; FID safe mask unverified. Read-only in HMI")
    add(19, "ID NBR", "User-assigned identifier", section="communication", access="RW", minimum="0", maximum="65535" if fid else "99", write_policy="validated", category="General")
    add(20, "SPEED", "Response / noise filter setting", section="calibration", access="RW", choices=(1, 2, 3) if fid or lel else (0, 1, 2, 3), write_policy="validated", restrictions="LEL 0 (off) only K-type; deferred to verification. LEL D default 1, others 2")
    add(21, "ADDRESS", "Displayed device address", section="communication", access="RW", minimum="1", maximum="255", restrictions="Packet-address offset requires read-only validation; reconnection procedure required", category="Communication")
    for n, name in [(22, "SET BAUD"), (47, "BAUD RATE")]:
        add(n, name, "Default baud setting" if n == 22 else "Currently active baud setting", section="communication", access="RW", choices=tuple(range(0x10, 0x17)), restrictions="0x10..0x16 = 19200,9600,4800,2400,1200,600,300; reconnection procedure required", category="Communication")
    ranges = {"SNR671": ("1.4", "3.0"), "SNR672": ("1.4", "2.7"), "SNR674": ("1.4", "2.5"), "SNR675": ("1.4", "2.3")}
    scaled(23, "LOW FLOW" if lel else "SET VAC", "Low-flow fault threshold" if lel else "Vacuum control setpoint", "flow" if lel else "fid_vacuum" if fid else "btu_vacuum", unit="SL/min" if lel else "inH2O", access="RW",
           model_ranges=ranges if lel else {}, minimum="-45" if fid else None, maximum="-30" if fid else None,
           write_policy="validated" if lel else "blocked", restrictions="FID -45..-30 inH2O / -11.2..-7.4 kPa, default -40 / -10. BTU typically 40; sign/range unverified" if not lel else "Assembly-dependent limits; default 1.4", category="General")
    temp_ranges = {"SNR671": ("50", "65"), "SNR672": ("100", "153"), "SNR674": ("100", "210"), "SNR675": ("100", "280")}
    scaled(24, "SET TEMP", "Housing-temperature setpoint", "temperature", unit="degC", access="RW", model_ranges=temp_ranges if lel else {} if fid else {"SNR692": ("100", "153")}, minimum="60" if fid else None, maximum="210" if fid else None, write_policy="validated", restrictions="Defaults: LEL 60/120/200/250 by base model; BTU SNR692 120; FID 200", category="General")
    for n, name in [(25, "4 MA ADJ"), (31, "20 MA ADJ")]:
        scaled(n, name, "Factory-set analog-output adjustment", "current_trim", unit="mA", section="outputs", access="RW", minimum=None if fid else "-2", maximum=None if fid else "2", restrictions="Factory calibration: read-only in initial release")
    for n, name in [(26, "MA CAL"), (32, "MA FAULT"), (44, "MA TEST")]:
        scaled(n, name, "Analog-output override during calibration / fault / test", "current", unit="mA", section="outputs", access="RW" if n != 44 or fid else "R-panel", minimum=None if fid or n == 44 else "2.5", maximum=None if fid or n == 44 else "22.7",
               restrictions="Also documented in reading format. MA TEST: menu-only for LEL/BTU; FID write safety unverified. Defaults MA CAL 22.1 mA / MA FAULT 21.0 for LEL/BTU")
    add(28, "CAL TIME", "Duration of each calibration interval", section="calibration", unit="min", access="RW", minimum="1", maximum="4", write_policy="validated", category="Calibration")
    for n, name in [(29, "RAW ZERO"), (30, "RAW SPAN"), (56, "SPAN VDC" if fid else "SPAN degC")]:
        scaled(n, name, "Zero-cal result" if n == 29 else "Span minus raw zero" if n == 30 else "Expected span-calibration rise", "voltage" if fid else "temperature", unit="VDC" if fid else "degC", section="calibration", access="RW" if n == 56 else "R",
               restrictions="LEL RAW ZERO 450..550 default500; BTU 200..300 default250. LEL SPAN standard105..140 default125; P68..140 default80; D/K50..70 default60. Calibration editing deferred" if not fid else "FID voltage range not documented", category="Calibration")
    if not fid:
        add(35, "AUTO IGN", "Automatic re-ignition attempts, 15-second spacing", section="alarms", access="RW", minimum="0", maximum="120", restrictions="0 disabled; default0. Safety-related behavior editing deferred")
    for n, name in [(36, "CONTROL1"), (37, "CONTROL2")]:
        add(n, name, "Command assigned to external control input", section="outputs", access="RW", restrictions="Encoding ambiguous (FID says except9,10); command remapping disabled")
    for n, name in [(38, "PEAK HI"), (39, "PEAK LOW")]:
        scaled(n, name, "Peak measurement since last reset", "reading")
    if not fid:
        add(40, "VERSION POINTER", "Internal version-display pointer: do not use", safe_read=False, restrictions="Internal; excluded from inspection and polling")
        add(42, "CHK FLOW" if lel else "UNNAMED", "Service-needed flow threshold" if lel else "Meaning not supplied", section="gauges", conversion="flow" if lel else "raw", signed=lel, unit="SL/min" if lel else "", restrictions="Explicitly do not write via Modbus", safe_read=lel)
        scaled(43, "CAL RDNG (last)", "Copy of CAL RDNG at last successful calibration", "reading", section="calibration", restrictions="Conversion inherited from explicit copy description")
    add(45, "RLY TEST", "Relays activated during test; RELAYS format", section="outputs", access="RW" if fid else "R-panel", restrictions="Menu-only and no Modbus writes LEL/BTU; FID operational writes blocked")
    add(46, "DUMMY", "No function; communications debugging", access="R" if fid else "RW", restrictions="FID lacks writable symbol; no debug-write bypass")
    add(48, "AUTOBAUD", "Automatic baud detection: 0 fixed, 1 auto", section="communication", access="RW", choices=(0, 1), restrictions="Communication changes deferred", category="Communication")
    if not fid:
        add(49, "RELAYS / FAILSAFE", "RELAYS low byte, FAILSAFE high byte")
        scaled(50, "OUTPUT READING", "READING including MA CAL / MA FAULT / MA TEST overrides", "reading", restrictions="Copy semantics documented; do not use as primary process reading")
        for n in range(51, 56):
            add(n, f"DISPLAY {n - 50}", "LCD display buffer, ASCII word", conversion="raw", restrictions="Decode ASCII only; layout/length not specified")
    if lel:
        add(41, "LINEAR", "D/K air dilution linear range: off40%LFL / on80%LFL", choices=(0, 1), restrictions="Legacy/menu-only history; no writable symbol; read-only")
        add(57, "MA SCALE", "%LFL equal to 20 mA:100; legacy D/K<=5.08 100 or200", restrictions="Conversion not specified; expose raw")
    add(58, "RLY CNFG", "Horn relay: 0 horn / 1 air-fuel / 2 always energized", section="outputs", access="RW", choices=(0, 1, 2), restrictions="Changes relay behavior; initial release read-only")
    if not fid:
        add(59, "SERVICE", "Service flags 0000 0000 A0RD LSZF; BTU F is N/A")
    add(60, "CAL LOCK", "Bit0 hardware lock; bit1 software lock", section="calibration")
    if lel:
        add(61, "RATE", "Rate-of-rise alarm enable", section="alarms", access="RW", choices=(0, 1), restrictions="Safety-related alarm editing deferred")
    if not fid:
        add(62, "TYPE", "Factory-programmed assembly type", section="alarms", restrictions="LEL codes0..13 listed in specification; factory read-only")
        add(63, "SERIAL", "Factory serial sequence; production year in ASCII identification", section="alarms")
        add(64, "LANGUAGE", "0 English / 1 German", section="alarms", access="RW", choices=(0, 1), write_policy="validated", category="General")
    end = 288 if fid else 272
    for number in range(257, end + 1):
        add(number, f"IDENT {number}", "ASCII identification: model, software, assembly, year / serial", section="alarms" if fid else "diagnostics", restrictions="Exact field positions must be verified; do not invent serial if year only")
    statuses = BASE_STATUSES.copy()
    if lel:
        statuses.update({20: "Flow low", 21: "Flow high"})
    else:
        statuses.update({16: "Vacuum low", 17: "Vacuum high"})
    if family == "BTU":
        statuses.update({1: "Low alarm", 2: "High alarm"})
    if fid:
        statuses.update({4: "Zero calibration", 5: "Span calibration"})
    return Profile(family, regs, statuses, end, not fid)
