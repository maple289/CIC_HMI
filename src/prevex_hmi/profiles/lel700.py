"""700-series definitions: H7FTA700 Rev D, printed/PDF pages 115–127.

Independent inventory: legacy register meanings are deliberately not inherited.
All configuration remains read-only pending validated procedures.
"""
from prevex_hmi.registers.schema import Profile, Register

STATUSES = dict(enumerate((
    "Normal", "Warning", "Danger / danger flooded", "Downscale", "Zero On", "Span On",
    "Purging", "Calibration ending", "Zero calibration failed", "Span failed: low",
    "Span failed: high", "Warmup", "Self test", "Self test failed", "Data lost",
    "12VDC failed", "Dilution low", "Dilution high", "Block temperature low",
    "Block temperature high", "Sample flow low", "Sample flow high", "Fuel pressure low",
    "Fuel pressure high", "TC1 failed", "TC2 failed", "Flameout", "ROM failed",
)))
TYPES = {16:"SNR701",17:"SNR702",18:"SNR704",19:"SNR705",20:"SNR701D",21:"SNR702D",22:"SNR704D",23:"SNR705D"}
GAUGES = (1,2,38,39,9,24,15,11,29,30)
SERVICE = {0:"Check Flow",1:"Check Zero",2:"Check Span",4:"Check Data",5:"Check Reading",8:"Check Dilution",9:"Check Fuel",10:"Check Enclosure",11:"Check Utilities",12:"Check Relays",13:"Check 4-20mA",14:"Check TC3"}


def make_profile():
    regs = {}
    def add(n,name,meaning,conversion="raw",unit="",page=125,access="R",minimum=None,maximum=None,restrictions=""):
        regs[n]=Register(n,name,meaning,conversion=conversion,signed=conversion!="raw",unit=unit,access=access,minimum=minimum,maximum=maximum,source=f"H7FTA700 Rev D p.{page}",restrictions=restrictions,write_policy="blocked")
    for n,name in ((1,"FLAMMABILITY"),(5,"WARNING LEVEL"),(6,"DANGER LEVEL"),(7,"CAL READING"),(10,"ZERO ADJUSTMENT"),(38,"PEAK HIGH %LFL"),(39,"PEAK LOW %LFL"),(43,"RDNG LAST CAL"),(50,"MILLIAMP OUTPUT"),(91,"ZERO AS FOUND"),(92,"SPAN AS FOUND"),(99,"RDNG FAULT LEVEL")):
        add(n,name,"Flammability in %LFL", "reading",page=117 if n==1 else 119 if n in (38,39) else 122 if n in (5,6,99) else 123 if n==50 else 121,access="RW" if n in (5,6,7,10) else "R")
    for n,name in ((9,"BLOCK TEMP"),(11,"FLAME TEMP"),(24,"BLOCK SETTING"),(29,"ZERO FLAME TEMP"),(30,"SPAN FLAME TEMP"),(56,"SPAN TEMP SET"),(71,"BLOCK TEMP LIMIT")):
        add(n,name,"Flame-cell temperature / calibration temperature", "temperature700","degC",119 if n in GAUGES else 121 if n==56 else 126,access="RW" if n in (24,56) else "R",restrictions="Model/temperature-class limits require verified context" if n==24 else "")
    for n,name in ((15,"SAMPLE FLOW"),(23,"LOW FLOW LEVEL"),(42,"CHECK FLOW SET"),(70,"CAL SAMPLE FLOW")):
        add(n,name,"Sample flow in standard liters/minute","flow","SL/min",119,access="RW" if n in (23,42) else "R")
    for n,name in ((12,"FUEL PRESSURE"),(13,"DILUTION PRESS"),(66,"DILUTION SETTING"),(67,"DILUTION LIMIT"),(68,"FUEL SETTING"),(69,"FUEL LIMIT"),(95,"FUEL PRESS ADJ"),(96,"DILN PRESS ADJ")):
        add(n,name,"Pressure; optional monitor hardware and setting required","pressure_bar","bar",120,access="RW" if n in (66,67,68,69) else "R",restrictions="Factory adjustments read-only; monitor availability must be verified")
    for n,name,conversion,unit in ((14,"ENCLOSURE PRESSURE","pressure_hpa","hPa"),(97,"ENCL PRESS ADJ","pressure_hpa","hPa"),(93,"ORF PRESSURE","pressure_kpa","kPa"),(94,"ORF PRESS ADJ","pressure_kpa","kPa")):
        add(n,name,"Pressure monitor / factory adjustment",conversion,unit,119 if n in (93,94) else 120)
    for n,name in ((25,"4MILLIAMP ADJUST"),(26,"MILLIAMP CAL SET"),(32,"MILLIAMP FAULT"),(44,"MIN MILLIAMP")):
        add(n,name,"Analog output adjustment / override","current_trim" if n==25 else "reading","mA" if n==25 else "%LFL",123,access="RW",restrictions="p123 says reading units; p116 LookupTenthsMA conversion conflicts. Editing blocked pending verification.")
    raw = {2:"STATUS",3:"FULL SCALE",4:"RELAYS",8:"COMMANDS",16:"A/D REF",17:"ALARM LATCH",18:"SAFETY RELAYS",19:"ID NUMBER",20:"SPEED SETTING",21:"MODBUS ADDRESS",22:"DEFAULT BAUD",27:"LOCK STATE",28:"CALIBRATION TIME",31:"20MA ADJUST",33:"CONTROL 3",34:"CONTROL 4",35:"AUTO IGNITION",36:"CONTROL 1",37:"CONTROL 2",41:"LINEARITY SET",45:"RELAY TESTS",46:"DUMMY REG",47:"CURRENT BAUD",48:"BAUD AUTO ADJUST",49:"RELAY STATES",57:"MILLIAMP SCALE",58:"RELAY SETTING",59:"SERVICE",60:"LOCK SETTING",61:"RATE ALARM",62:"DEVICE TYPE",63:"SERIAL NUMBER",64:"LANGUAGE",65:"YEAR BUILT",72:"WARNING LATCH",73:"DANGER LATCH",74:"FAULT LATCH",100:"MINIMUM SPEED",102:"FUEL MONITOR",103:"DILUTION MONITOR",104:"PURGE MONITOR",105:"CHECK RELAY NE"}
    for n,name in raw.items():
        page=127 if n in (3,4,16,17,18,31,41,49,57) else 126 if n in (27,45,46,59,60) else 118 if n==8 else 117 if n==2 else 124 if n in (19,21,22,47,48) else 122 if n in (35,61,72,73,74) else 121 if n in (20,28) else 123 if n in (33,34,36,37,58,105) else 125
        add(n,name,"Enumerated / integer setting; see source table",page=page,access="command" if n==8 else "RW" if n in (19,20,21,22,28,33,34,35,36,37,48,58,60,61,64,72,73,74) else "R")
    add(40,"SOFTWARE VERSION","Numeric firmware version","version",page=125)
    add(98,"FLAME TC GAIN","Factory thermocouple gain","percent","%",125,access="RW",restrictions="Factory calibration; read-only initial release")
    add(101,"RESPONSE TIME","Last full-calibration response time","tenths_seconds","s",121)
    add(106,"TC TIME CONST","Thermocouple time constant","tenths_seconds","s",125,restrictions="p127 contradicts p125: says no valid register above105. Inspection blocked pending verification.")
    from dataclasses import replace
    bounds={1:("-128","127"),5:("5","60"),6:("10","60"),7:("40","80"),10:("-3","3"),19:("0","99"),21:("1","32"),23:("1.4","2.4"),27:("0","3"),28:("1","4"),29:("460","525"),30:("37","175"),35:("0","120"),38:("-128","128"),39:("-128","128"),42:("0.2","0.6"),43:("40","80"),50:("-10","125"),56:("50","150"),60:("0","3"),63:("100","9999"),65:("2001","2100"),66:("0","1.72"),67:("0.03","0.34"),68:("0","1.72"),69:("0.03","0.34"),94:("-4","4"),95:("-0.10","0.10"),96:("-0.10","0.10"),97:("-2.5","2.5"),98:("95","115"),99:("-20","-10"),106:("9","12")}
    for n,(low,high) in bounds.items():regs[n]=replace(regs[n],minimum=low,maximum=high)
    for n in (48,61,64,72,73,74,100,102,103,104,105):regs[n]=replace(regs[n],choices=(0,1))
    regs[58]=replace(regs[58],choices=(0,1,2))
    regs[20]=replace(regs[20],choices=(0,1,2,3),restrictions="0 permitted only with verified MINIMUM SPEED100; no editing")
    regs[62]=replace(regs[62],choices=tuple(n for n in range(1,24) if n not in (14,15)),restrictions="Factory type; no writes")
    regs[22]=replace(regs[22],restrictions="Baud code mapping requires verification; p124 lists14/15=38400,16=19200,17=9600")
    regs[47]=replace(regs[47],restrictions=regs[22].restrictions)
    regs[106]=replace(regs[106],safe_read=False)
    for n in range(51,56):add(n,"DISABLED LEGACY DISPLAY","Legacy LCD buffer disabled",page=127)
    for n in range(75,91):add(n,f"DISPLAY BUFFER {n-74}","Two-line sixteen-character front panel ASCII buffer",page=126)
    return Profile("LEL",regs,STATUSES,256,False,revision="700")


PROFILE = make_profile()
