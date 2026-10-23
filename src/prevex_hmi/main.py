from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

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
    args=parser.parse_args()
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
    window=MainWindow(settings,settings_path,data_path)
    window.show()
    errors=[]
    if args.smoke_test:
        def finish():
            try:
                if window.update_count < 2:
                    raise RuntimeError("No worker updates received")
                if not window.snapshot or window.snapshot["quality"] != "GOOD":
                    raise RuntimeError("Single simulated analyzer is not current")
                if not window.identity.get("controls_verified"):
                    raise RuntimeError("Automatic instrument identification failed")
                for index,name in [(0,"overview"),(0,"detail"),(1,"trends"),(4,"diagnostics")]:
                    window.navigation.setCurrentRow(index)
                    app.processEvents()
                    if not window.grab().save(str(data_path/f"{name}.png")):
                        raise RuntimeError("Window rendering failed")
                (data_path/"smoke-report.json").write_text(json.dumps({"result":"PASS","mode":"simulation","updates":window.update_count,"devices":1,"detected_family":window.identity.get("family"),"gauge_parameters":len(window.readouts),"physical_access":False},indent=2),encoding="utf-8")
                print(f"PASS: single-analyzer GUI, updates={window.update_count}, detected={window.identity.get('family')}")
            except Exception as error:
                errors.append(str(error))
                print(f"FAIL: {error}")
            finally:
                window.close()
        QTimer.singleShot(4000,finish)
    result=app.exec()
    return 1 if errors else result


if __name__ == "__main__":
    raise SystemExit(main())
