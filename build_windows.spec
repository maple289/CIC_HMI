# Build on Windows using the locked Python 3.12 development environment.
from pathlib import Path
import ssl

root = Path(SPECPATH)
# Some managed Python runtimes ship ssl.py with a required companion PEM.
# Preserve that resource rather than altering certificate verification behavior.
ssl_companion=Path(ssl.__file__).with_name('codex-rejected-cas.pem')
runtime_data=[(str(ssl_companion),'.')] if ssl_companion.is_file() else []
runtime_data.append((str(root/'src'/'prevex_hmi'/'assets'/'fonts'),'prevex_hmi/assets/fonts'))
a = Analysis(
    [str(root / 'scripts' / 'run_hmi.py')],
    pathex=[str(root / 'src')],
    binaries=[], datas=runtime_data, hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=['PyQt5', 'PyQt6', 'PySide2'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PREVEX-HMI',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PREVEX-HMI')
