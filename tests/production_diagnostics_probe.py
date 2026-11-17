"""Disconnected production Diagnostics geometry; no serial I/O."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication,QPushButton,QComboBox
from prevex_hmi.devices.configuration import load_settings
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.gui.fonts import configure_application_font
folder=Path(sys.argv[1]);app=QApplication([]);configure_application_font(app)
w=MainWindow(load_settings(folder/'settings.json'),folder/'settings.json',folder)
try:
    w.showMaximized();w.show_diagnostics('Modbus')
    for _ in range(6):app.processEvents()
    layout=w.traffic.parentWidget().layout();export=next(b for b in w.findChildren(QPushButton) if b.text()=='Export Diagnostics JSON')
    assert not any('simulat' in b.text().lower() or 'resume dynamic' in b.text().lower() for b in w.findChildren(QPushButton))
    assert w.inspect_button.text()=='Inspect register'
    inspection_row=layout.itemAt(layout.indexOf(export)+1).layout()
    assert inspection_row is not None and inspection_row.indexOf(w.inspect_button)>=0
    assert w.traffic.height()>w.height()*.40,(w.traffic.height(),w.height())
    w.traffic.setRowCount(100);app.processEvents();assert w.traffic.verticalScrollBar().maximum()>0
    report={'scale':app.primaryScreen().devicePixelRatio(),'window':w.size().toTuple(),'traffic_height':w.traffic.height(),'inspection':w.inspect_button.text(),'physical_access':False}
    folder.mkdir(exist_ok=True);(folder/'report.json').write_text(json.dumps(report));w.grab().save(str(folder/'diagnostics.png'))
finally:
    w.close()
    for _ in range(20):app.processEvents()
    if w.recording_worker.isRunning():w.recording_worker.wait(5000)
