# Default remains the working one-folder development package.
from pathlib import Path
import json,os,ssl
root=Path(SPECPATH)
stage=Path(os.environ['PREVEX_BUILD_STAGE']).resolve() if os.environ.get('PREVEX_BUILD_STAGE') else None
onefile=os.environ.get('PREVEX_BUILD_LAYOUT','onedir')=='onefile'
ssl_companion=Path(ssl.__file__).with_name('codex-rejected-cas.pem')
runtime_data=[(str(ssl_companion),'.')] if ssl_companion.is_file() else []
assets=(stage/'prevex_hmi/assets') if stage else root/'src/prevex_hmi/assets'
runtime_data.append((str(assets),'prevex_hmi/assets'))
icon=str(assets/'prevex-hmi.ico')
hidden=json.loads((stage/'build-options.json').read_text(encoding='utf-8'))['hiddenimports'] if stage else []
native=list(stage.glob('prevex_hmi*.pyd')) if stage else []
if stage and len(native)!=1:raise RuntimeError('Protected build requires one native application package')
a=Analysis(
    [str(stage/'launcher.py') if stage else str(root/'scripts/run_hmi.py')],
    pathex=[str(stage) if stage else str(root/'src')],
    binaries=[(str(native[0]),'.')] if stage else [],datas=runtime_data,hiddenimports=hidden,
    hookspath=[],hooksconfig={},runtime_hooks=[],
    excludes=['PyQt5','PyQt6','PySide2','pytest','tests','tkinter','IPython']+(['prevex_hmi'] if stage else []),
    noarchive=False,optimize=0,
)
if stage and any(name=='prevex_hmi' or name.startswith('prevex_hmi.') for name,*rest in a.pure):
    raise RuntimeError('Readable application bytecode leaked into protected build')
if stage:
    # Third-party hooks may collect editor-only Qt typing stubs as data.
    a.datas=[entry for entry in a.datas if not entry[0].lower().endswith(('.pyi','.pdb','.c','.cpp'))]
pyz=PYZ(a.pure)
options=dict(name='PREVEX-HMI',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
             console=os.environ.get('PREVEX_BUILD_CONSOLE')=='1',disable_windowed_traceback=bool(stage),icon=icon)
if onefile:
    exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],**options)
else:
    exe=EXE(pyz,a.scripts,[],exclude_binaries=True,**options)
    coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='PREVEX-HMI')
