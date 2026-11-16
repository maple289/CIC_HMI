"""Native-compile the readable source in staging, then use the proven packager."""
import argparse,ast,base64,importlib.util,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from release_integrity import ROOT,envelope,signing_key


def external_imports(package):
    names=set()
    for file in package.rglob('*.py'):
        for node in ast.walk(ast.parse(file.read_text(encoding='utf-8-sig'))):
            if isinstance(node,ast.Import):names.update(a.name for a in node.names)
            elif isinstance(node,ast.ImportFrom) and not node.level and node.module:
                names.add(node.module)
                if not node.module.startswith('prevex_hmi'):
                    for alias in node.names:
                        if alias.name=='*':continue
                        candidate=node.module+'.'+alias.name
                        try:
                            if importlib.util.find_spec(candidate) is not None:names.add(candidate)
                        except (ImportError,AttributeError,ValueError):pass
    return sorted(n for n in names if not n.startswith('prevex_hmi') and n not in ('__future__',))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind',choices=['development','protected'],default='protected')
    parser.add_argument('--layout',choices=['onedir','onefile'],default='onefile')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/protected-release')
    parser.add_argument('--compiler',choices=['mingw64','msvc'],default='mingw64')
    parser.add_argument('--jobs',type=int,default=4)
    parser.add_argument('--manifest-signing-key',type=Path)
    args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'dist'):raise ValueError('Build output must be inside the project dist directory')
    if args.jobs<1:raise ValueError('Compiler jobs must be positive')
    env=os.environ.copy();env['PREVEX_BUILD_LAYOUT']=args.layout;env.pop('PREVEX_BUILD_STAGE',None)
    work=ROOT/'build';work.mkdir(exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='protected-',dir=work))
    key=signing_key(args.manifest_signing_key) if args.manifest_signing_key else None
    env.pop('PREVEX_MANIFEST_KEY_PASSWORD',None)  # Never pass signing secrets to compiler/packager/report subprocesses.
    if args.kind=='protected':
        source=stage/'source/prevex_hmi';shutil.copytree(ROOT/'src/prevex_hmi',source,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        guard=source/'security/integrity.py';text=guard.read_text(encoding='utf-8')
        public=base64.b64encode(key.public_key().public_bytes_raw()).decode() if key else ''
        text=text.replace('_PROTECTED = False','_PROTECTED = True').replace("_PUBLIC_KEY = ''",f'_PUBLIC_KEY = {public!r}')
        guard.write_text(text,encoding='utf-8')
        native=stage/'native';env['NUITKA_CACHE_DIR']=str(ROOT/'.venv/nuitka-cache')
        command=[sys.executable,'-m','nuitka','--mode=package',str(source),'--include-package=prevex_hmi',
                 '--nofollow-imports','--no-pyi-stubs','--python-flag=no_docstrings','--update-check=never',
                 '--assume-yes-for-downloads',f'--jobs={args.jobs}',f'--output-dir={native}',f'--report={stage / "native-report.xml"}',
                 '--mingw64' if args.compiler=='mingw64' else '--msvc=latest']
        subprocess.run(command,cwd=ROOT,env=env,check=True)
        binaries=list(native.glob('prevex_hmi*.pyd'))
        if len(binaries)!=1:raise RuntimeError('Expected exactly one compiled application package')
        runtime=stage/'runtime';runtime.mkdir();shutil.copy2(binaries[0],runtime/binaries[0].name)
        shutil.copytree(source/'assets',runtime/'prevex_hmi/assets')
        manifest=runtime/'prevex_hmi/assets/integrity.json'
        paths=[p for p in runtime.rglob('*') if p.is_file() and p!=manifest]
        manifest.write_text(json.dumps(envelope(runtime,paths,key),indent=2),encoding='utf-8')
        (runtime/'build-options.json').write_text(json.dumps({'hiddenimports':external_imports(source)}),encoding='utf-8')
        (runtime/'launcher.py').write_text('''import sys
try:
    from prevex_hmi.main import main
    result=main()
except Exception as error:
    if not any(flag in sys.argv for flag in ('--smoke-test','--verify-installation')):
        raise
    print('FAIL: packaged component could not load:',error,file=sys.stderr)
    result=3
raise SystemExit(result)
''',encoding='utf-8')
        env['PREVEX_BUILD_STAGE']=str(runtime)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(output),'--workpath',str(stage/'packaging'),str(ROOT/'build_windows.spec')],cwd=ROOT,env=env,check=True)
    release=[p for p in output.rglob('*') if p.is_file() and p.name!='release-manifest.json']
    (output/'release-manifest.json').write_text(json.dumps(envelope(output,release,key),indent=2),encoding='utf-8')
    # Build record stays in build/, never in the distributed software.
    (stage/'build-result.json').write_text(json.dumps({'kind':args.kind,'layout':args.layout,'output':str(output),'manifest_signed':bool(key)},indent=2),encoding='utf-8')
    print(f'Build complete: {output}; evidence: {stage}')


if __name__=='__main__':main()
