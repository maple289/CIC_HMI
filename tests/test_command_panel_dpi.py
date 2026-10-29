"""Each process has its own actual Qt screen geometry and fractional scale."""
import json,os,subprocess,sys,uuid
from pathlib import Path
import pytest


@pytest.mark.parametrize('width,height,scale',[(1920,1080,1),(1920,1080,1.25),(1920,1080,1.5),(2560,1440,1.25)])
def test_command_panel_screen_matrix(tmp_path,width,height,scale):
    root=Path(__file__).resolve().parents[1]
    # Qt's platform arguments use colons as separators, so Windows drive-letter
    # paths cannot be supplied here. CI's TEMP and checkout may be on different
    # drives; keep this small config in the checkout and use a relative path.
    config=root/'tmp'/f'command-screen-{uuid.uuid4().hex}.json';config.parent.mkdir(exist_ok=True)
    # Reserve 60 physical pixels for taskbar/decorations; all layout decisions
    # remain Qt device-independent. The offscreen plugin uses native dimensions.
    config.write_text(json.dumps(dict(screens=[dict(name='Test desktop',width=width,height=height-60,logicalDpi=96,logicalBaseDpi=96,dpr=1.)])))
    env=os.environ.copy();env.update(QT_QPA_PLATFORM='offscreen:configfile='+os.path.relpath(config,root),QT_SCALE_FACTOR=str(scale),QT_SCALE_FACTOR_ROUNDING_POLICY='PassThrough')
    data=tmp_path/'layout'
    try:result=subprocess.run([sys.executable,str(root/'tests/command_panel_probe.py'),str(data)],cwd=root,env=env,capture_output=True,text=True,timeout=150)
    finally:config.unlink(missing_ok=True)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    report=json.loads((data/'report.json').read_text());assert len(report['cases'])==24 and not report['physical_access']
    assert report['dpr']==pytest.approx(scale)
    assert report['screen'][2]==pytest.approx(width/scale,abs=1)
    for case in report['cases']:
        assert case['stable'] and case['rows_height']>=400
        if case['mode']=='maximized' and scale!=1.5:assert case['scroll_max']==0
