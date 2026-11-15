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
    reported_version: str = ""
    version_provisional: bool = False


def model_family(model):
    if re.fullmatch(r'SNR(?:67[0-9]|70[0-9])[A-Z]*',model):return 'LEL'
    if re.fullmatch(r'SNR69[0-9][A-Z]*',model):return 'BTU'
    if re.fullmatch(r'SNR65[0-9][A-Z]*',model):return 'FID'
    return None


def identity_key(identity):
    """Physical identity excludes informational firmware/formatting."""
    # Preserve opaque trailing identifiers when an older header has no labeled
    # serial field. Removing firmware gates must not permit swapping same-model
    # controllers that report different unparsed unit identifiers.
    suffix=''
    if not identity.serial and identity.model and identity.model.upper() in identity.text.upper():
        tail=re.split(re.escape(identity.model),identity.text,maxsplit=1,flags=re.I)[1]
        suffix=' '.join(re.sub(r'\bVER\s*\S+','',tail,flags=re.I).upper().split())
    return identity.family,identity.model,identity.serial,suffix


def parse_identity(text: str) -> Identification:
    clean=text.replace('\x00',' ').strip()
    model=re.search(r'\bSNR\d+[A-Z]*\b',clean.upper())
    model=model.group(0) if model else ''
    inferred=model_family(model)
    explicit=set(re.findall(r'\b(?:LEL|BTU|FID)\b',clean.upper()))
    legacy=bool(re.match(r'^TYPE\s+FTAVER\s',clean,re.I))
    if legacy:explicit.add('LEL')
    if inferred:explicit.add(inferred)
    if not explicit and 'PREVEX' in clean.upper():explicit.add('LEL')
    if len(explicit)!=1:return Identification(text=clean,warning='Unknown or conflicting analyzer identity')
    family=explicit.pop()
    version=re.search(r'(?:\bVER|(?<=FTA)VER)\s*(\d+)([.\xa7])(\d+(?:\.\d+)?)',clean,re.I)
    normalized=f'{version[1]}.{version[3]}' if version else 'Unknown'
    reported=f'{version[1]}{version[2]}{version[3]}' if version else ''
    serial=re.search(r'(?:SERIAL\s*[:#]?|S/N\s*[:#]?)\s*([A-Z0-9-]+)',clean.upper())
    if serial is None and family=='FID':serial=re.search(r'\b(\d{2}\s+\d{3,})\s*$',clean)
    warning='' if inferred==family else 'Model unavailable or outside the documented analyzer series; verify identification'
    return Identification(family=family,model=model,version=normalized,serial=serial[1] if serial else '',text=clean,warning=warning,verified=bool(model and inferred==family),legacy_format=legacy,reported_version=reported)


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
                try:version_word=bus.read(LEL700,addressing,40,1)[40]
                except (OSError,ValueError):version_word=None
                serial_word=bus.read(LEL700,addressing,63,1)[63]
                year_word=bus.read(LEL700,addressing,65,1)[65]
                if not 100 <= serial_word <= 9999 or not 2001 <= year_word <= 2100:
                    return Identification(warning='700-series identity registers inconsistent; manual verification required')
                model=TYPES700[type_word]
                version=f'{version_word//100}.{version_word%100:02d}' if type(version_word) is int and 0<version_word<32768 else 'Unknown'
                serial=f'{year_word%100:02d}-{serial_word}'
                return Identification('LEL',model,version,serial,f'LEL {model} VER {version} S/N {serial} (numeric identification)',verified=True)
        if identity.family == "FID":
            if alternate_page:
                return replace(identity,verified=False,warning="FID alternate identification page is undocumented")
            # Physical FID continuation remains blocked by the existing profile gate.
            words.update(bus.read(PROFILES["FID"],addressing,273,16))
            identity=parse_identity(ascii_words(words))
        if identity.family == "LEL":
            model_word=bus.read(PROFILES["LEL"],addressing,62,1)[62]
            model=LEL_TYPES.get(model_word,"")
            if model and identity.model and model != identity.model:
                return replace(identity,verified=False,warning="ASCII assembly conflicts with LEL TYPE register62")
            if not identity.model and model:
                identity=replace(identity,model=model,warning='' if identity.warning.startswith('Model unavailable') else identity.warning)
        if identity.family and identity.model:
            return replace(identity,verified=not bool(identity.warning))
        return replace(identity,warning=identity.warning or "Model unavailable; manual verification required")
    except (OSError,ValueError,PermissionError) as error:
        return Identification(warning=f"Identification failed: {error}")


def resolve_profile(config, selection: str, identity: Identification):
    from prevex_hmi.profiles import normalize_selection
    selected_family=normalize_selection(selection)
    family=identity.family or (selected_family if selected_family in PROFILES else None)
    if family is None:
        warning="Auto Detect could not recognize the instrument. Choose a type manually."
        if identity.warning:warning+=' '+identity.warning
        return None,warning,False
    from prevex_hmi.profiles.lel670 import MODELS
    identified_series='700' if identity.model in TYPES700.values() else '670' if identity.model in MODELS else None
    selected_series=None
    mismatch=selected_family in PROFILES and identity.family is not None and (selected_family != identity.family or selected_series is not None and identified_series is not None and selected_series != identified_series)
    warning=f"PROFILE MISMATCH: selected {selection}, detected {identity.family} {identified_series or ''}. Using detected profile; commands blocked." if mismatch else identity.warning
    if mismatch and identity.warning:warning+=' '+identity.warning
    if family=='LEL' and identity.model and identified_series is None:
        warning=(warning+' '+f'Undocumented LEL assembly {identity.model}; model-specific conversion and controls unavailable. Manufacturer verification required.').strip()
    if not identity.verified and not warning:
        warning="Identity unverified; commands blocked"
    # Never interpret BTU/FID registers using a contradictory selected profile.
    effective=replace(config,family=family,assembly=identity.model or config.assembly,version=identity.version or 'Unknown',register_profile=(identified_series or config.register_profile if config.family==family else identified_series or 'auto') if family=='LEL' else 'auto')
    return effective, warning, bool(identity.verified and not mismatch and not warning)
