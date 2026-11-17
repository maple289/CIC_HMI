import json,os,subprocess,sys,uuid
from pathlib import Path
import pytest


@pytest.mark.parametrize('scale',[1,1.25,1.5])
def test_production_diagnostics_uses_recovered_space_at_windows_scaling(tmp_path,scale):
    root=Path(__file__).resolve().parents[1];config=root/'tmp'/f'production-screen-{uuid.uuid4().hex}.json';config.parent.mkdir(exist_ok=True)
    config.write_text(json.dumps({'screens':[{'name':'Production screen','width':1920,'height':1020,'logicalDpi':96,'logicalBaseDpi':96,'dpr':1.}]}),encoding='utf-8')
    env=os.environ.copy();env.update(QT_QPA_PLATFORM='offscreen:configfile='+os.path.relpath(config,root),QT_SCALE_FACTOR=str(scale),QT_SCALE_FACTOR_ROUNDING_POLICY='PassThrough')
    try:result=subprocess.run([sys.executable,str(root/'tests/production_diagnostics_probe.py'),str(tmp_path/'ui')],cwd=root,env=env,capture_output=True,text=True,timeout=30)
    finally:config.unlink(missing_ok=True)
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads((tmp_path/'ui/report.json').read_text(encoding='utf-8'));assert report['inspection']=='Inspect register' and not report['physical_access']
