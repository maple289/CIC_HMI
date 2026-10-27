"""Visible full-row selection and manager workflow; isolated simulated data."""
from PySide6.QtCore import Qt,QItemSelectionModel
from PySide6.QtGui import QColor,QPalette
import pytest
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.devices.configuration import load_settings
from prevex_hmi.logging_db.recordings import RecordingStore
from test_recording_sessions import sample,stamp
from test_monitoring import app,until


@pytest.fixture
def manager(app,tmp_path):
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path,start_worker=False)
    w.users.create_user('admin','password8');w.session=w.users.authenticate('admin','password8')
    store=RecordingStore(tmp_path/'simulation.sqlite3');ids=[]
    for second in range(3):
        sid,params=store.start(sample(second),1,False,'manual',stamp(second),selected=[1])
        store.append(sid,sample(second),params,{},stamp(second));store.end(sid,'Stopped',stamp(second+1));ids.append(sid)
    store.close();w.recording_management.keep(w.session,[ids[1]],True)
    w.show();w.trend_window.manage_data();dialog=w.trend_window.management_window
    until(app,lambda:not dialog.busy);dialog.resize(1500,700);app.processEvents()
    yield w,dialog
    w.close();until(app,lambda:not w.recording_worker.isRunning() and not w.record_jobs);app.processEvents()


def selected_background(dialog,row):
    rect=dialog.table.visualItemRect(dialog.table.item(row,3))
    image=dialog.table.viewport().grab().toImage();ratio=image.devicePixelRatio()
    return image.pixelColor(round(rect.center().x()*ratio),round((rect.bottom()-4)*ratio))


@pytest.mark.parametrize('theme,highlight,foreground',[
    ('dark','#226fa5','#ffffff'),('light','#b8d9f5','#102a43')])
def test_selection_rendered_with_contrast_after_focus_moves(app,manager,theme,highlight,foreground):
    w,d=manager;w.settings['theme']=theme;w.apply_theme();d.table.setFocus();d.table.selectRow(0);app.processEvents()
    assert selected_background(d,0)==QColor(highlight)
    assert selected_background(d,1)!=QColor(highlight)
    d.refresh_button.setFocus();app.processEvents()
    assert selected_background(d,0)==QColor(highlight)
    for group in (QPalette.Active,QPalette.Inactive):
        assert d.table.palette().color(group,QPalette.Highlight)==QColor(highlight)
        assert d.table.palette().color(group,QPalette.HighlightedText)==QColor(foreground)
    assert '1 selected' in d.selection_summary.text() and d.export_button.isEnabled()


def test_multiselection_survives_refresh_reordering_and_live_theme_change(app,manager):
    w,d=manager;d.table.selectRow(0)
    d.table.selectionModel().select(d.table.model().index(1,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
    selected={r['id'] for r in d.selected()};assert len(selected)==2
    data=d.service.inventory();data['sessions'].reverse();d.show_inventory(data);app.processEvents()
    assert {r['id'] for r in d.selected()}==selected and '2 selected' in d.selection_summary.text()
    assert d.keep_button.isEnabled() and d.unkeep_button.isEnabled() and d.delete_button.isEnabled()
    w.settings['theme']='light';w.apply_theme();app.processEvents()
    assert {r['id'] for r in d.selected()}==selected
    for index in d.table.selectionModel().selectedRows():assert selected_background(d,index.row())==QColor('#b8d9f5')
    d.table.clearSelection();assert not d.export_button.isEnabled() and not d.delete_button.isEnabled() and not d.keep_button.isEnabled()
    assert d.selection_summary.text()=='No recordings selected'


def test_actions_follow_selection_protection_and_role(app,manager):
    w,d=manager
    assert d.tabs.tabText(0)=='Recordings' and d.tabs.tabText(1)=='Retention and maintenance'
    protected=next(i for i,r in enumerate(d.rows) if r['protected']);d.table.selectRow(protected)
    assert d.unkeep_button.isEnabled() and not d.keep_button.isEnabled() and not d.delete_button.isEnabled()
    assert '1 protected' in d.selection_summary.text()
    w.users.logout(w.session);d.update_access()
    assert d.export_button.isEnabled() and not d.unkeep_button.isEnabled() and not d.apply.isEnabled()
