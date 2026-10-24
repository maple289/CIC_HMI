"""Explicit user-approved compatibility assumptions, not hardware validation."""
from prevex_hmi.profiles.lel670 import MODELS


def assumed_481(model: str, version: str) -> bool:
    return model in MODELS and version == '4.81'
