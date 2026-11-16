"""Presentation and offline integrity checks; never open serial ports."""
import base64,hashlib,json,os,struct,subprocess,sys
from pathlib import Path
import pytest
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel,QDialog
from prevex_hmi.gui.about import AboutDialog
from prevex_hmi.security import attribution,integrity
from prevex_hmi.gui.branding import application_icon
from test_command_result_layout import app,setup_window,flush


def test_profile_table_seven_columns_keeps_restrictions_selection_and_read(app,tmp_path,monkeypatch):
    w,bus,snap=setup_window(tmp_path,'LEL')
    try:
        table=w.settings_table
        assert [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]==['Register','Menu','Parameter','Raw','Value','Units','Documented access']
        row=next(i for i in range(table.rowCount()) if table.item(i,0).text()=='18')
        assert 'Modbus' in table.item(row,6).toolTip() or 'modbus' in table.item(row,6).toolTip() or 'prohibit' in table.item(row,6).toolTip()
        table.selectRow(row);before=table.item(row,0).text()
        calls=[];monkeypatch.setattr(w,'request',lambda *args:calls.append(args));w.read_setting_button.setEnabled(True)
        w.read_setting();assert calls==[('inspect',18)]
        w.refresh_profile_settings();assert table.item(table.currentRow(),0).text()==before
        w.show();w.navigation.setCurrentRow(1);w.service_tabs.setCurrentIndex(1)
        for width in (1100,1540):
            w.resize(width,900);flush(app)
            assert table.columnCount()==7 and sum(table.columnWidth(i) for i in range(7))>=table.viewport().width()-5
    finally:w.close();bus.close();flush(app)


@pytest.mark.parametrize('theme',['light','dark'])
def test_about_content_and_both_access_paths(app,tmp_path,monkeypatch,theme):
    w,bus,_=setup_window(tmp_path,'LEL');w.settings['theme']=theme;w.apply_theme();w.show();flush(app)
    opened=[]
    def inspect(dialog):
        text='\n'.join(label.text() for label in dialog.findChildren(QLabel))
        for expected in ('PREVEX HMI','Industrial Analyzer Monitoring & Control','Alexander Alexeev, C.E.T.','Certified Engineering Technologist','Software Version: 1.0','© 2026 Alexander Alexeev. All rights reserved.'):
            assert expected in text
        assert not dialog.windowIcon().isNull();opened.append(True);return QDialog.Rejected
    monkeypatch.setattr(AboutDialog,'exec',inspect)
    try:
        assert any(a.text()=='Help' for a in w.menuBar().actions())
        w.about_action.trigger();assert len(opened)==1
        w.activateWindow();w.raise_();flush(app)
        QTest.keyClick(w,Qt.Key_A,Qt.ControlModifier|Qt.AltModifier|Qt.ShiftModifier);flush(app)
        assert len(opened)==2
    finally:w.close();bus.close();flush(app)


def test_icon_multiresolution_and_encoded_attribution(app):
    path=Path(__file__).resolve().parents[1]/'src/prevex_hmi/assets/prevex-hmi.ico'
    raw=path.read_bytes();reserved,kind,count=struct.unpack_from('<HHH',raw)
    assert (reserved,kind)==(0,1) and count==7
    assert [struct.unpack_from('<B',raw,6+i*16)[0] or 256 for i in range(count)]==[16,24,32,48,64,128,256]
    icon=application_icon();assert not icon.isNull()
    for size in (16,24,32,48,64,128,256):assert not icon.pixmap(size,size).isNull()
    source=Path(attribution.__file__).read_bytes()
    assert b'Alexander Alexeev' not in source and b'Certified Engineering Technologist' not in source


def test_changed_attribution_rejected(monkeypatch):
    monkeypatch.setattr(attribution,'_PACKED',attribution._PACKED[:-3]+'abc')
    with pytest.raises(ValueError):attribution.developer_information()


def manifest(root):
    return {'payload':{'schema':1,'files':{'asset.bin':integrity.file_digest(root/'asset.bin')}},'signature':''}


def test_unsigned_manifest_detects_changes_missing_files_and_traversal(tmp_path):
    file=tmp_path/'asset.bin';file.write_bytes(b'original');data=manifest(tmp_path)
    assert integrity.verify_manifest(tmp_path,data,required=['asset.bin'])['signature']=='unsigned'
    file.write_bytes(b'tampered')
    with pytest.raises(integrity.IntegrityError):integrity.verify_manifest(tmp_path,data)
    file.unlink()
    with pytest.raises(integrity.IntegrityError):integrity.verify_manifest(tmp_path,data)
    for bad in ('../asset.bin','C:/asset.bin','folder\\asset.bin'):
        data['payload']['files']={bad:'0'*64}
        with pytest.raises(integrity.IntegrityError):integrity.verify_manifest(tmp_path,data)


def test_manifest_signature_requires_independently_trusted_key(tmp_path):
    pytest.importorskip('cryptography')
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key=Ed25519PrivateKey.generate();(tmp_path/'asset.bin').write_bytes(b'protected');data=manifest(tmp_path)
    data['signature']=base64.b64encode(key.sign(integrity.canonical(data['payload']))).decode()
    public=base64.b64encode(key.public_key().public_bytes_raw()).decode()
    assert integrity.verify_manifest(tmp_path,data,public)['signature']=='verified'
    for trusted in ('',base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode()):
        with pytest.raises(integrity.IntegrityError):integrity.verify_manifest(tmp_path,data,trusted)
    data['payload']['files']['asset.bin']='0'*64
    with pytest.raises(integrity.IntegrityError):integrity.verify_manifest(tmp_path,data,public)


def test_startup_integrity_failure_preserves_databases_and_never_starts_monitoring(tmp_path):
    db=tmp_path/'hardware.sqlite3';db.write_bytes(b'operator history must remain unchanged');before=hashlib.sha256(db.read_bytes()).hexdigest()
    code='''import sys
from prevex_hmi.security import integrity
from prevex_hmi import main
integrity.verify_startup=lambda:(_ for _ in ()).throw(integrity.IntegrityError('test alteration'))
sys.argv=['hmi','--verify-installation','--data-dir',sys.argv[1]]
raise SystemExit(main.main())'''
    env=os.environ.copy();env['QT_QPA_PLATFORM']='offscreen';env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path)],env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==3 and 'software_integrity_failed' in result.stderr
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    assert sorted(p.name for p in tmp_path.iterdir())==['hardware.sqlite3']


def test_native_packaging_discovers_from_package_submodules(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    from build_release import external_imports
    (tmp_path/'imports.py').write_text('from serial.tools import list_ports\nfrom PySide6.QtWidgets import QLabel\n')
    modules=external_imports(tmp_path)
    assert 'serial.tools.list_ports' in modules and 'serial.tools' in modules
    assert 'PySide6.QtWidgets' in modules and 'PySide6.QtWidgets.QLabel' not in modules
