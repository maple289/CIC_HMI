# Build on Windows using the locked Python 3.12 development environment.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / 'scripts' / 'run_hmi.py')],
    pathex=[str(root / 'src')],
    binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=['PyQt5', 'PyQt6', 'PySide2'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PREVEX-HMI',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PREVEX-HMI')
