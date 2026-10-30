"""Make name-only OFL derivatives with collision-free application families.

Developer tool: fonttools==4.60.1 in the local virtual environment. Inputs are
the unmodified pinned Noto files listed in assets/fonts/SOURCE.json. FontTools
is not an application/runtime dependency; generated fonts are committed.
"""
import hashlib,json,sys
from pathlib import Path
from fontTools.ttLib import TTFont

root=Path(__file__).resolve().parents[1]/'src'/'prevex_hmi'/'assets'/'fonts'
source=Path(sys.argv[1])
manifest=json.loads((root/'SOURCE.json').read_text())
original=manifest['files'];output={}
for recorded_name,info in original.items():
    if recorded_name=='OFL.txt':output[recorded_name]=info;continue
    old_name=info.get('upstream_file',recorded_name)
    path=source/old_name
    expected=info.get('upstream_sha256',info['sha256'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('Upstream font checksum mismatch: '+old_name)
    symbols='Symbols2' in old_name
    style='Regular' if symbols else old_name.removeprefix('NotoSans-').removesuffix('.ttf')
    family='PREVEX Symbols' if symbols else 'PREVEX UI '+style
    filename=('PrevexSymbols-' if symbols else 'PrevexUI-')+style+'.ttf'
    font=TTFont(path,recalcTimestamp=False);names=font['name']
    values={1:family,2:style,3:f'{family} {style}; PREVEX name-only derivative',4:f'{family} {style}',6:family.replace(' ','')+'-'+style,16:family,17:style}
    for identifier in (1,2,3,4,6,16,17,21,22,25):names.removeNames(nameID=identifier)
    for identifier,value in values.items():names.setName(value,identifier,3,1,0x409)
    font.save(root/filename);font.close();data=(root/filename).read_bytes()
    output[filename]={**info,'upstream_file':old_name,'upstream_sha256':expected,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
manifest['modifications']='Name table only: separate PREVEX UI Regular/SemiBold/Bold and PREVEX Symbols families to avoid native Windows font-family collisions and face overwrites. Glyphs and metrics are unchanged.'
manifest['generator']='scripts/prepare_ui_fonts.py with fonttools 4.60.1'
manifest['files']=output
(root/'SOURCE.json').write_text(json.dumps(manifest,indent=2)+'\n')
