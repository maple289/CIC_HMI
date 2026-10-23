from decimal import Decimal

import pytest

from prevex_hmi.profiles import PROFILES
from prevex_hmi.registers.schema import Context, UnverifiedDefinition, decode_relays, decode_service


CONTEXT = {
    "LEL": Context(assembly="SNR675", version="5.11"),
    "BTU": Context(assembly="SNR692", version="5.20"),
    "FID": Context(assembly="SNR650", version="4.80", fullscale=100, units="US"),
}


@pytest.mark.parametrize("family,number,raw,expected,unit", [
    ("LEL", 1, 25600, "100", "%LFL"),
    ("LEL", 1, 0xFF00, "-1", "%LFL"),
    ("BTU", 1, 25600, "1000", "unit unverified"),
    ("FID", 1, 25600, "100", "PPM"),
    ("LEL", 15, 1000, "1.72936", "SL/min"),
    ("LEL", 9, 1000, "244.26", "degC"),
    ("BTU", 23, 100, "35.1734", "inH2O"),
    ("BTU", 33, 100, "10.5862", "PSIG"),
    ("FID", 10, 0xFC18, "-35.1734", "inH2O"),
    ("FID", 33, 100, "10.5882", "psi"),
    ("FID", 56, 1000, "2.4426", "VDC"),
    ("LEL", 26, 1600, "5", "mA"),
    ("BTU", 25, 0xFFF6, "-1", "mA"),
])
def test_manufacturer_examples(family, number, raw, expected, unit):
    value, actual_unit = PROFILES[family].register(number).decode(raw, family, CONTEXT[family])
    assert value == Decimal(expected)
    assert actual_unit == unit


SCALED = [(f, n) for f,p in PROFILES.items() for n,r in p.registers.items() if r.signed]


@pytest.mark.parametrize("family,number", SCALED)
@pytest.mark.parametrize("raw", [0, 1, 32767, 32768, 65535])
def test_every_documented_scaled_register_roundtrips(family, number, raw):
    r = PROFILES[family].register(number)
    engineering, _ = r.decode(raw, family, CONTEXT[family])
    assert r.encode(engineering, family, CONTEXT[family]) == raw


@pytest.mark.parametrize("version,expected", [("5.08", "200"), ("5.8", "200"), ("5.09", "100"), ("5.11", "100")])
@pytest.mark.parametrize("assembly", ["SNR674D", "SNR675K"])
def test_legacy_dilution(version, expected, assembly):
    assert PROFILES["LEL"].register(1).decode(25600, "LEL", Context(assembly, version))[0] == Decimal(expected)


def test_reading_refuses_missing_context():
    with pytest.raises(UnverifiedDefinition):
        PROFILES["LEL"].register(1).decode(100, "LEL", Context())
    for context in (Context(), Context(fullscale=100), Context(fullscale=0, units="US")):
        with pytest.raises(UnverifiedDefinition):
            PROFILES["FID"].register(1).decode(100, "FID", context)


def test_fid_metric_factors_are_independent():
    context = Context(fullscale=1000, units="METRIC")
    assert PROFILES["FID"].register(1).decode(25600, "FID", context) == (Decimal(1000), "MG")
    assert PROFILES["FID"].register(10).decode(100, "FID", context) == (Decimal("0.879336"), "kPa")
    assert PROFILES["FID"].register(33).decode(100, "FID", context) == (Decimal("72.9412"), "kPa")


def test_family_meanings_and_unsupported_registers():
    assert PROFILES["LEL"].register(23).name == "LOW FLOW"
    assert PROFILES["BTU"].register(23).name == "SET VAC"
    assert PROFILES["FID"].register(56).conversion == "voltage"
    assert PROFILES["BTU"].register(56).conversion == "temperature"
    for family, number in [("FID",59), ("LEL",10), ("BTU",15), ("FID",64), ("LEL",273)]:
        with pytest.raises(UnverifiedDefinition):
            PROFILES[family].register(number)


@pytest.mark.parametrize("bit,label", list(enumerate(("Warning / low", "Danger / high", "Fault", "Horn", "Zero valve", "Span valve", "Ignition", "Heater"))))
def test_relay_bit_order(bit, label):
    flags = decode_relays(1 << bit)
    assert flags[label] and sum(flags.values()) == 1


def test_status_and_service_mappings():
    assert PROFILES["BTU"].status(1) == "Low alarm"
    assert PROFILES["LEL"].status(20) == "Flow low"
    assert PROFILES["FID"].status(16) == "Vacuum low"
    assert "Unknown" in PROFILES["FID"].status(20)
    assert decode_service(1, "LEL")["CHK_FLOW"]
    assert "CHK_FLOW" not in decode_service(1, "BTU")
    with pytest.raises(UnverifiedDefinition):
        decode_service(0, "FID")


@pytest.mark.parametrize("family,number", [("LEL",18), ("LEL",42), ("LEL",44), ("BTU",45), ("FID",25), ("FID",18), ("BTU",21), ("LEL",8)])
def test_prohibited_or_unverified_writes_blocked(family, number):
    with pytest.raises(PermissionError):
        PROFILES[family].register(number).validate_simulated_write(0, family, CONTEXT[family])


def test_known_ranges_model_limits_and_quantization():
    lel = PROFILES["LEL"]
    lel.register(28).validate_simulated_write(4, "LEL", CONTEXT["LEL"])
    with pytest.raises(ValueError):
        lel.register(28).validate_simulated_write(5, "LEL", CONTEXT["LEL"])
    context = Context("SNR671", "5.11")
    r = lel.register(24)
    r.validate_simulated_write(r.encode(65, "LEL", context), "LEL", context)
    with pytest.raises(ValueError):
        r.validate_simulated_write(r.encode(100, "LEL", context), "LEL", context)
    with pytest.raises(UnverifiedDefinition):
        r.validate_simulated_write(100, "LEL", Context("unknown", "5.11"))


@pytest.mark.parametrize("bad", [-1, 65536, True, 1.5])
def test_invalid_raw_values_rejected(bad):
    with pytest.raises(ValueError):
        PROFILES["LEL"].register(1).decode(bad, "LEL", CONTEXT["LEL"])


def test_nonfinite_inverse_rejected():
    for value in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError):
            PROFILES["BTU"].register(1).encode(value, "BTU", CONTEXT["BTU"])
