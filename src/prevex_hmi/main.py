from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

from prevex_hmi.devices.configuration import load_settings
from prevex_hmi.gui.window import MainWindow


class JsonFormatter(logging.Formatter):
    def format(self, record):
        result={"time":self.formatTime(record),"level":record.levelname,"logger":record.name,"message":record.getMessage()}
        for name in ("device_address","register_number","error_kind","detail"):
            if hasattr(record,name): result[name]=getattr(record,name)
        if record.exc_info: result["exception"]=self.formatException(record.exc_info)
        return json.dumps(result)


def main() -> int:
    parser=argparse.ArgumentParser(description="PREVEX HMI - one active analyzer. Physical access remains gated pending authorization.")
    parser.add_argument("--data-dir",type=Path,help="Override the user-writable data directory")
    parser.add_argument("--smoke-test",action="store_true",help="Run offscreen monitoring checks and exit")
    parser.add_argument('--read-only-com4',action='store_true',help='Explicitly authorize the tested COM4/9600/address1 SNR671 read-only bench session')
    parser.add_argument('--controller-com4-bench',action='store_true',help='Authorized SNR671 COM4 bench monitoring with confirmed Operator ACK/RESET only')
    args=parser.parse_args()
    if args.smoke_test and (args.read_only_com4 or args.controller_com4_bench):parser.error('Automated smoke tests cannot open hardware')
    if args.smoke_test:
        os.environ["QT_QPA_PLATFORM"]="offscreen"
    app=QApplication(sys.argv[:1])
    app.setApplicationName("PREVEX HMI")
    app.setOrganizationName("CIC")
    font_path=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"/"segoeui.ttf"
    if font_path.is_file():
        font_id=QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0: app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0],10))
    if args.smoke_test and args.data_dir is None:
        parser.error("--smoke-test requires --data-dir to isolate test data")
    data_path=(args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))).resolve()
    data_path.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(data_path/"application.log",maxBytes=2_000_000,backupCount=3,encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO,handlers=[handler])
    settings_path=data_path/"settings.json"
    try:
        settings=load_settings(settings_path)
    except (OSError,ValueError,KeyError,TypeError) as error:
        logging.exception("configuration_load_failed")
        if args.smoke_test:
            print(f"FAIL: {error}")
        else:
            QMessageBox.critical(None,"Configuration error",f"Could not load {settings_path}\n{error}\nThe existing file was preserved.")
        return 2
    if args.smoke_test and settings['mode']!='simulation':
        print('FAIL: automated smoke data directory must contain simulation settings')
        return 2
    grant=None
    if args.read_only_com4 or args.controller_com4_bench:
        from prevex_hmi.communication.hardware_session import ReadOnlyControllerGrant,controller_bench_settings
        grant=ReadOnlyControllerGrant(operator_commands=args.controller_com4_bench)
        settings=controller_bench_settings(settings)
    window=MainWindow(settings,settings_path,data_path,hardware_grant=grant)
    window.show()
    errors=[]
    if args.smoke_test:
        export_results=[];hidden_samples=[]
        def start_recording():
            window.open_trend();window.recording_worker.request('start')
        def hide_trend():
            hidden_samples.append(window.recording_status.get('samples',0));window.trend_window.close()
        def export_recording():
            from prevex_hmi.logging_db.recordings import export_csv
            session=window.recording_status.get('session')
            if not session:errors.append('Recording session did not start');return
            window.record_job(lambda:export_csv(window.trend_window.paths,data_path/'recording.csv',session=session),export_results.append,errors.append)
        QTimer.singleShot(750,start_recording)
        QTimer.singleShot(3000,hide_trend)
        QTimer.singleShot(6500,export_recording)
        heartbeat_times=[]
        heartbeat=QTimer(window);heartbeat.setInterval(100)
        heartbeat.timeout.connect(lambda:heartbeat_times.append(time.monotonic()));heartbeat.start()
        diagnostic_updates=[]
        def open_diagnostics():
            window.navigation.setCurrentRow(4)
            diagnostic_updates.append(window.update_count)
        QTimer.singleShot(1500,open_diagnostics)
        def finish():
            try:
                # Import client dependencies without opening any port. Packaged
                # simulation must also verify that the serial runtime can load.
                from prevex_hmi.communication.serial_transport import ReadOnlySerialTransport
                if window.update_count < 2:
                    raise RuntimeError("No worker updates received")
                if not window.snapshot or window.snapshot["quality"] != "GOOD":
                    raise RuntimeError("Single simulated analyzer is not current")
                if not window.identity.get("controls_verified"):
                    raise RuntimeError("Automatic instrument identification failed")
                gap=max((b-a for a,b in zip(heartbeat_times,heartbeat_times[1:])),default=0)
                active_updates=window.update_count-diagnostic_updates[0] if diagnostic_updates else 0
                if gap > 1.5 or active_updates < 8 or window.traffic.rowCount()!=100:
                    raise RuntimeError(f"Diagnostics responsiveness failed: heartbeat gap={gap:.2f}s, updates={active_updates}, rows={window.traffic.rowCount()}")
                if not window.trend_window.isWindow() or not hidden_samples or window.recording_status.get('samples',0)<=hidden_samples[0] or not export_results or export_results[0]<1:
                    raise RuntimeError('Detached Trend / hidden recording / asynchronous CSV export failed')
                if window.trend_window.live_plot.zero_line.value()!=0:raise RuntimeError('Trend zero reference missing')
                for index,name in [(0,"overview"),(0,"detail"),(1,"trends"),(4,"diagnostics")]:
                    window.navigation.setCurrentRow(index)
                    if name=='trends':window.open_trend()
                    app.processEvents()
                    target=window.trend_window if name=='trends' else window
                    if not target.grab().save(str(data_path/f"{name}.png")):
                        raise RuntimeError("Window rendering failed")
                (data_path/"smoke-report.json").write_text(json.dumps({"result":"PASS","mode":"simulation","updates":window.update_count,"devices":1,"detected_family":window.identity.get("family"),"gauge_parameters":len(window.readouts),"diagnostics_updates":active_updates,"maximum_heartbeat_gap_ms":round(gap*1000,1),"physical_access":False,"trend_detached":True,"hidden_recording":True,"recorded_frames":window.recording_status['samples'],"exported_frames":export_results[0]},indent=2),encoding="utf-8")
                print(f"PASS: single-analyzer GUI, updates={window.update_count}, detected={window.identity.get('family')}")
            except Exception as error:
                errors.append(str(error))
                print(f"FAIL: {error}")
            finally:
                window.close()
        QTimer.singleShot(12000,finish)
    result=app.exec()
    return 1 if errors else result


if __name__ == "__main__":
    raise SystemExit(main())
