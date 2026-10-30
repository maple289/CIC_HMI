import json,os,subprocess,sys,uuid
from pathlib import Path


def test_connected_fault_layout_fits_recommended_laptop_size(tmp_path):
    root=Path(__file__).resolve().parents[1]
    config=root/'tmp'/f'laptop-size-{uuid.uuid4().hex}.json';config.parent.mkdir(exist_ok=True)
    # Match the supplied screenshot's 72 physical pixels occupied by the taskbar.
    config.write_text(json.dumps(dict(screens=[dict(name='Laptop',width=1920,height=1008,logicalDpi=96,logicalBaseDpi=96,dpr=1.)])))
    env=os.environ.copy();env.update(QT_QPA_PLATFORM='offscreen:configfile='+os.path.relpath(config,root),QT_SCALE_FACTOR=str(1.5*.85),QT_SCALE_FACTOR_ROUNDING_POLICY='PassThrough')
    output=tmp_path/'layout'
    try:result=subprocess.run([sys.executable,str(root/'tests/laptop_display_probe.py'),str(output)],cwd=root,env=env,capture_output=True,text=True,timeout=60)
    finally:config.unlink(missing_ok=True)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    report=json.loads((output/'report.json').read_text());assert len(report)==2
    assert all(case['command_scroll_max']==0 for case in report)
