"""Inspect a packaged release without executing application or serial code."""
import argparse,json,struct
from pathlib import Path
import pefile
from PyInstaller.archive.readers import CArchiveReader


def audit(executable):
    executable=Path(executable)
    pe=pefile.PE(str(executable))
    resources={entry.id:entry for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries if entry.id is not None}
    count=len(resources[3].directory.entries)  # RT_ICON; verifies PE embedding, not a loose icon.
    if count<7:raise ValueError('Executable does not contain all seven icon images')
    archive=CArchiveReader(str(executable));pyz=archive.open_embedded_archive('PYZ.pyz')
    readable=[name for name in pyz.toc if name=='prevex_hmi' or name.startswith('prevex_hmi.')]
    if readable:raise ValueError('Application bytecode present in protected PYZ: '+repr(readable))
    entries=list(archive.toc)
    internal=executable.parent/'_internal'
    if internal.is_dir():entries.extend(p.relative_to(internal).as_posix() for p in internal.rglob('*') if p.is_file())
    unwanted=[name for name in entries if name.replace('\\','/').startswith(('tests/','scripts/','Docs/')) or name.endswith(('.pdb','.pyi','.c','.cpp'))]
    if unwanted:raise ValueError('Development files in release: '+repr(unwanted))
    if not any(name.startswith('prevex_hmi') and name.endswith('.pyd') for name in archive.toc):
        # One-folder binaries are adjacent to the EXE, rather than in CArchive.
        native=list((executable.parent/'_internal').glob('prevex_hmi*.pyd'))
        if len(native)!=1:raise ValueError('No protected native application')
        native_bytes=native[0].read_bytes()
    else:
        name=next(name for name in archive.toc if name.startswith('prevex_hmi') and name.endswith('.pyd'))
        native_bytes=archive.extract(name)
    for phrase in ('Alexander Alexeev','Certified Engineering Technologist','All rights reserved.'):
        for encoding in ('utf-8','utf-16-le'):
            if phrase.encode(encoding) in native_bytes:raise ValueError('Readable attribution found in native module')
    return {'exe':str(executable),'embedded_icon_images':count,'application_pyz_modules':len(readable),'native_package':True,'attribution_plaintext_found':False,'development_files_found':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('executable',type=Path)
    print(json.dumps(audit(p.parse_args().executable),indent=2))
