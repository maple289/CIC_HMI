"""Read-only manufacturer identity probing; no writes or address scanning."""
from dataclasses import asdict, dataclass, replace
import re

from prevex_hmi.profiles import PROFILES
from prevex_hmi.profiles.lel700 import PROFILE as LEL700, TYPES as TYPES700
from prevex_hmi.registers.schema import Profile, Register

PROBE = Profile("IDENTIFICATION", {n:Register(n,"IDENT","ASCII identification") for n in range(257,289)}, {}, 288, True)
LEL_TYPES = dict(enumerate(("", "SNR671", "SNR671D", "SNR672P", "SNR672", "SNR672D", "SNR672K", "SNR674P", "SNR674PL", "SNR674", "SNR674D", "SNR675", "SNR675D", "SNR675K")))
LEL_TYPES.update(TYPES700)


@dataclass(frozen=True)
class Identification:
    family: str | None = None
    model: str = ""
    version: str = ""
    serial: str = ""
    text: str = ""
    warning: str = ""
    verified: bool = False
    legacy_format: bool = False


def parse_identity(text: str) -> Identification:
    clean=text.replace("\x00"," ").strip()
    if re.match(r'^TYPE\s+FTAVER\s',clean,re.I) and re.search(r'\b(?:BTU|FID)\b',clean,re.I):
        return Identification(text=clean,warning='Conflicting legacy FTA/analyzer family identity')
    # Observed on the explicitly authorized SNR671 controller. Preserve the
    # source glyph; interpreting A7 as a version separator remains provisional.
    if re.match(r'^TYPE\s+FTAVER\s',clean,re.I) and re.search(r'\bSNR67[1245](?:D|K|P|PL)?\b',clean,re.I) and not re.search(r'\b(?:BTU|FID)\b',clean,re.I):
        model=re.search(r'\bSNR67[1245](?:D|K|P|PL)?\b',clean,re.I).group(0).upper()
        version=re.search(r'VER\s*(\d+)([.\xa7])(\d{2})\b',clean,re.I)
        return Identification(family='LEL',model=model,version=f'{version[1]}.{version[3]}' if version else '',text=clean,warning='Legacy FTA compatibility profile: firmware separator and older register support remain provisional. Only explicitly authorized operator commands are permitted.',legacy_format=True)
    tokens=set(re.findall(r"\b(?:LEL|PREVEX|BTU|FID)\b",clean.upper()))
    families={"LEL" if t == "PREVEX" else t for t in tokens}
    if len(families) != 1:
        return Identification(text=clean,warning="Unknown or conflicting analyzer identity")
    family=families.pop()
    model=re.search(r"\bSNR\d+[A-Z]*\b",clean.upper())
    version=re.search(r"\bVER\s*(\d+\.\d+(?:\.\d+)?)",clean.upper())
    serial=re.search(r"(?:SERIAL\s*[:#]?|S/N\s*[:#]?)\s*([A-Z0-9-]+)",clean.upper())
    if serial is None and family == "FID":
        serial=re.search(r"\b(\d{2}\s+\d{3,})\s*$",clean)
    return Identification(family,model.group(0) if model else "",version.group(1) if version else "",serial.group(1) if serial else "",clean)


def detect(bus, addressing, *, alternate_page=False) -> Identification:
    def ascii_words(words):
        return b"".join(words[n].to_bytes(2,"big") for n in sorted(words)).decode("latin-1")
    try:
        try:
            words=bus.read(PROBE,addressing,1025 if alternate_page else 257,16)
        except (OSError,ValueError):
            words={}
        identity=parse_identity(ascii_words(words))
        if identity.family is None and not identity.text and not alternate_page:
            # Rev D p127 removes ASCII257+. Recognized 700 TYPE is required
            # before reading40: that register is internal on older instruments.
            type_word=bus.read(PROFILES['LEL'],addressing,62,1)[62]
            if type_word in TYPES700:
                version_word=bus.read(LEL700,addressing,40,1)[40]
                serial_word=bus.read(LEL700,addressing,63,1)[63]
                year_word=bus.read(LEL700,addressing,65,1)[65]
                if not 700 <= version_word < 800 or not 100 <= serial_word <= 9999 or not 2001 <= year_word <= 2100:
                    return Identification(warning='700-series identity registers inconsistent; manual verification required')
                model=TYPES700[type_word]
                version=f'{version_word//100}.{version_word%100:02d}'
                serial=f'{year_word%100:02d}-{serial_word}'
                return Identification('LEL',model,version,serial,f'LEL {model} VER {version} S/N {serial} (numeric identification)',verified=True)
        if identity.family == "FID":
            if alternate_page:
                return replace(identity,warning="FID alternate identification page is undocumented")
            # Physical FID continuation remains blocked by the existing profile gate.
            words.update(bus.read(PROFILES["FID"],addressing,273,16))
            identity=parse_identity(ascii_words(words))
        if identity.family == "LEL" and not identity.legacy_format:
            model_word=bus.read(PROFILES["LEL"],addressing,62,1)[62]
            model=LEL_TYPES.get(model_word,"")
            if model and identity.model and model != identity.model:
                return replace(identity,warning="ASCII assembly conflicts with LEL TYPE register62")
            if not identity.model and model:
                identity=replace(identity,model=model)
        if identity.family and identity.model and identity.version:
            return replace(identity,verified=not bool(identity.warning))
        return replace(identity,warning=identity.warning or "Model or software version unavailable; manual verification required")
    except (OSError,ValueError,PermissionError) as error:
        return Identification(warning=f"Identification failed: {error}")


def resolve_profile(config, selection: str, identity: Identification):
    family=identity.family or (selection if selection in PROFILES else None)
    if family is None:
        return None, "Auto Detect could not recognize the instrument. Choose a type manually.", False
    mismatch=selection in PROFILES and identity.family is not None and selection != identity.family
    warning=f"PROFILE MISMATCH: selected {selection}, detected {identity.family}. Using detected profile; commands blocked." if mismatch else identity.warning
    if not identity.verified and not warning:
        warning="Identity unverified; commands blocked"
    # Never interpret BTU/FID registers using a contradictory selected profile.
    effective=replace(config,family=family,assembly=identity.model or config.assembly,version=identity.version or config.version,register_profile='fta_4x' if identity.legacy_format else 'auto')
    return effective, warning, bool(identity.verified and not mismatch and not identity.warning)
