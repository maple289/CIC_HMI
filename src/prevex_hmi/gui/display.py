"""Application-wide size preference, applied once before QApplication exists."""
import json,os,sys
from PySide6.QtCore import QCoreApplication,QStandardPaths
from pathlib import Path


def application_data_path():
    QCoreApplication.setApplicationName('PREVEX HMI');QCoreApplication.setOrganizationName('CIC')
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))


def saved_size(path):
    try:value=json.loads(path.read_text(encoding='utf-8')).get('ui_scale','auto')
    except (OSError,ValueError,AttributeError):return 'auto'
    return value if value=='auto' or type(value) is int and value in (75,85,100) else 'auto'


def native_display_metrics():
    if sys.platform!='win32' or os.environ.get('QT_QPA_PLATFORM','').startswith('offscreen'):return None
    import ctypes
    from ctypes import wintypes
    try:
        user=ctypes.WinDLL('user32');gdi=ctypes.WinDLL('gdi32');shcore=ctypes.WinDLL('shcore')
        user.GetDC.argtypes=[wintypes.HWND];user.GetDC.restype=wintypes.HDC
        user.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
        gdi.GetDeviceCaps.argtypes=[wintypes.HDC,ctypes.c_int]
        user.MonitorFromPoint.argtypes=[wintypes.POINT,wintypes.DWORD];user.MonitorFromPoint.restype=wintypes.HANDLE
        shcore.GetScaleFactorForMonitor.argtypes=[wintypes.HANDLE,ctypes.POINTER(ctypes.c_int)]
        dc=user.GetDC(None)
        try:width,height=gdi.GetDeviceCaps(dc,118),gdi.GetDeviceCaps(dc,117)
        finally:user.ReleaseDC(None,dc)
        factor=ctypes.c_int();monitor=user.MonitorFromPoint(wintypes.POINT(0,0),1)
        if shcore.GetScaleFactorForMonitor(monitor,ctypes.byref(factor))!=0:return None
        return (width,height,factor.value)
    except (AttributeError,OSError):return None


def choose_size(preference,metrics):
    if type(preference) is int and preference in (75,85,100):return preference
    return 85 if metrics and 0<metrics[1]<=1200 and metrics[2]>=150 else 100


def apply_launch_size(preference,*,explicit=False,metrics=None):
    metrics=native_display_metrics() if metrics is None else metrics
    # Use Qt's shipped FreeType renderer consistently with the bundled faces.
    # Native GDI produced substituted/overwritten faces despite matching names.
    if sys.platform=='win32' and os.environ.get('QT_QPA_PLATFORM','') in ('','windows'):
        os.environ['QT_QPA_PLATFORM']='windows:fontengine=freetype'
    size=choose_size(preference,metrics)
    external=os.environ.get('QT_SCALE_FACTOR','')
    selected=explicit or type(preference) is int and preference in (75,85,100)
    if external and not selected:return dict(percent=None,source='environment',native=metrics)
    if size!=100 or selected:os.environ['QT_SCALE_FACTOR']=str(size/100)
    return dict(percent=size,source='automatic' if preference=='auto' else 'selected',native=metrics)


def size_dialog(parent,preference):
    from PySide6.QtWidgets import QComboBox,QDialog,QDialogButtonBox,QLabel,QVBoxLayout
    dialog=QDialog(parent);dialog.setWindowTitle('Display Size');box=QVBoxLayout(dialog)
    label=QLabel('Size of the entire HMI, including gauges, cards and commands.');label.setWordWrap(True);box.addWidget(label)
    choice=QComboBox()
    for text,value in (('Automatic — compact on small high-DPI screens','auto'),('Smaller — 75%',75),('Compact — 85%',85),('Windows default — 100%',100)):
        choice.addItem(text,value)
    choice.setCurrentIndex(max(0,choice.findData(preference)));box.addWidget(choice)
    note=QLabel('Save, then close and reopen the HMI to apply. Monitoring continues until you close the application. Windows display settings are unchanged.');note.setWordWrap(True);note.setMaximumWidth(420);box.addWidget(note)
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);box.addWidget(buttons)
    try:return choice.currentData() if dialog.exec()==QDialog.Accepted else None
    finally:dialog.deleteLater()
