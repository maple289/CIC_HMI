"""Application-local branding; works from source, one-folder and one-file."""
from pathlib import Path
from PySide6.QtGui import QIcon


def application_icon():
    return QIcon(str(Path(__file__).resolve().parents[1]/'assets'/'prevex-hmi.ico'))
