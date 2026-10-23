"""Run directly in VS Code, or pass --check for a headless environment check.

This standalone setup check does not open serial ports or communicate with devices.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sqlite3
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Run offscreen and exit automatically")
    args = parser.parse_args()
    if args.check:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    print(f"Python: {sys.version}")
    print(f"Interpreter: {sys.executable}")
    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12 or newer is required")

    versions: dict[str, str] = {}
    for distribution, module in (
        ("PySide6", "PySide6.QtWidgets"),
        ("pymodbus", "pymodbus.client"),
        ("pyserial", "serial"),
        ("pyqtgraph", "pyqtgraph"),
        ("numpy", "numpy"),
        ("pytest", "pytest"),
        ("pyinstaller", "PyInstaller"),
    ):
        importlib.import_module(module)
        versions[distribution] = importlib.metadata.version(distribution)
        print(f"PASS: {distribution} {versions[distribution]}")

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
    import pyqtgraph as pg

    with sqlite3.connect(":memory:") as database:
        database.execute("CREATE TABLE measurement (value REAL)")
        database.execute("INSERT INTO measurement VALUES (?)", (12.5,))
        value = database.execute("SELECT value FROM measurement").fetchone()[0]
        if json.loads(json.dumps({"value": value}))["value"] != 12.5:
            raise RuntimeError("SQLite / JSON round trip failed")
    print("PASS: SQLite and JSON round trip")

    app = QApplication.instance() or QApplication(sys.argv[:1])
    # The offscreen Qt platform may not discover Windows system fonts itself.
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font_path.is_file():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0:
            app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    window = QMainWindow()
    window.setWindowTitle("PREVEX HMI - Development Environment Check")
    window.resize(850, 550)
    content = QWidget()
    layout = QVBoxLayout(content)
    title = QLabel("PREVEX HMI | Environment check")
    title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 12px;")
    layout.addWidget(title)
    notice = QLabel("SIMULATED DATA - No instruments connected")
    notice.setStyleSheet("background: #fce6a6; color: #332500; padding: 12px; font-weight: bold;")
    layout.addWidget(notice)
    status = QLabel("Python, Qt, Modbus libraries, SQLite and JSON: PASS")
    status.setMargin(10)
    layout.addWidget(status)
    plot = pg.PlotWidget(background="#182230")
    plot.setLabel("left", "Synthetic signal", units="a.u.")
    plot.setLabel("bottom", "Sample")
    plot.showGrid(x=True, y=True, alpha=0.2)
    curve = plot.plot(pen=pg.mkPen("#43d6bd", width=2))
    layout.addWidget(plot)
    layout.addWidget(QLabel("Close this window when finished. This is a setup check, not the analyzer application."))
    window.setCentralWidget(content)

    tick_count = 0
    errors: list[str] = []

    def update() -> None:
        nonlocal tick_count
        tick_count += 1
        samples = list(range(max(0, tick_count - 120), tick_count + 120))
        curve.setData(samples, [math.sin(x / 16) * 10 + 30 for x in samples])
        status.setText(f"All library checks: PASS | GUI timer updates: {tick_count}")

    timer = QTimer(window)
    timer.timeout.connect(update)
    timer.start(50)
    window.show()

    if args.check:
        def finish() -> None:
            try:
                if tick_count < 3 or curve.xData is None:
                    raise RuntimeError("GUI timer / plot did not update")
                output = Path(__file__).resolve().parents[1] / "tmp" / "environment-check"
                output.mkdir(parents=True, exist_ok=True)
                screenshot = output / "window.png"
                if not window.grab().save(str(screenshot)):
                    raise RuntimeError("Could not render Qt window")
                report = {
                    "result": "PASS", "python": sys.version,
                    "executable": sys.executable, "libraries": versions,
                    "gui_updates": tick_count, "sqlite_json": "PASS",
                    "physical_devices_accessed": False,
                }
                (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(f"PASS: Qt event loop and PyQtGraph ({tick_count} updates)")
                print(f"Rendered window: {screenshot}")
            except Exception as error:
                errors.append(str(error))
            finally:
                app.quit()

        QTimer.singleShot(1000, finish)

    result = app.exec()
    if errors:
        raise RuntimeError("; ".join(errors))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
