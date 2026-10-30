# Commands panel: fractional DPI and focus-driven scrolling

## Laptop fonts and short client areas (2026-10-30)

The operator's later 1920x1080/150% screenshot showed mixed serif body/button text and sans-serif headings, and the 340-logical-pixel gauge row pushed the parameter cards below the initial view. The preceding Commands source and confirmation source have identical global dimensions at the same simulated DPI; no double scaling was established from that comparison.

Production now resolves and verifies a sans-serif UI family, registers the installed Segoe UI regular/semibold/bold faces consistently, and lets stylesheets inherit that resolved family. Previously production registered only the regular face while visual tests registered all three. Available Tahoma/Arial and other sans families provide fallback; Windows fonts are neither bundled nor installed. Qt documents the matching behavior in [QFont](https://doc.qt.io/qt-6/qfont.html). This addresses font selection without claiming that the exact laptop fallback cause has been reproduced.

Client windows at or below 760 Qt logical pixels high use a 230px minimum gauge/info row, 20px headings and reduced general-button/banner padding. Larger windows retain the 340px gauge row and prior headings. Body text stays 13px, command rows stay 40px, and Windows/Qt DPI remains in control. The setting depends on usable client height, including after resize or a monitor change; commands and their results do not select the layout. No global scale multiplier or fixed panel coordinates were introduced. At the simulated 150% laptop screen, the first measurement-card row is visible on opening, with independent readout/command scrolling still available.

Startup `application.log` includes a `display_configuration` entry with actual Qt platform, screen/work area, DPI, device pixel ratio, resolved body/heading font, UI pixel size, compact state and Qt scale environment overrides. Native Windows checks on MSI-PC (3840x2160 at 150%, resized to a laptop-sized client area) resolved Segoe UI with DPR 1.5 and no override. The specific laptop remains subject to an operator visual check. Screenshots/metrics: `tmp/laptop-corrected/`; native report: `tmp/native-display/display.json`.

## Reproduced cause

At a configured1920×1080 desktop /150% scale, reserving60 physical pixels for the taskbar, Qt reports1280×680 usable logical pixels. In the old maximized layout, the command viewport was471 logical pixels high and its content637 pixels high. ACK started at y265 and CAL LOCK at y751 in window coordinates. Clicking ACK disabled the focused button as part of the existing safety interlock. Qt transferred focus through the next still-enabled commands while they were being disabled. Scroll offsets changed0 →97 →151 →166; ACK ended at y99 and CAL LOCK at y585. Window, viewport and content sizes did not change. The apparent panel movement was **scrolling caused by focus transfer**, rather than command-result layout growth.

Qt6.8's [QScrollArea::focusNextPrevChild](https://raw.githubusercontent.com/qt/qtbase/6.8/src/widgets/widgets/qscrollarea.cpp) explicitly calls ensureWidgetVisible after transferring focus. Its default margin is50 logical pixels. This makes an interlock-driven focus walk particularly noticeable when the list overflows. The previous main-window minimum was also780 logical pixels high, unsuitable for a680-pixel work area in normal/windowed operation. Earlier layout tests used wide windows at1020 logical pixels high; scaling screenshots without reducing the logical desktop height did not reproduce the laptop condition.

Baseline evidence: tmp/command-layout-before.json and monitor.png in tmp/command-layout-before/. No physical command was issued: the UI confirmed a request to a stubbed simulation receiver.

## Corrections

- Command rows and actual pushbuttons are fixed at40 Qt logical pixels instead of48/46, a16.7% row-height reduction. Button padding is4px vertically, with a one-pixel pressed-label offset; spacing is4px instead of6. The existing3D borders, labels, padlock and16px acceptance LEDs remain. Row and button constraints keep enabled/disabled size hints from changing geometry. Timer behavior is unchanged.
- The existing236px sidebar width is preserved. Qt layouts position the panel; its heading, role and lock state remain above an expanding internal scroll area. Only the command rows scroll. Resizable content follows the viewport width, horizontal scrolling is disabled, and minimum/maximum layout constraints expose the full row list without clipping. Extra height goes into a bottom stretch, never between buttons.
- CommandScrollArea keeps focus transfer stationary when the previous focus widget has just been disabled. Normal keyboard traversal still reveals the next enabled command, using zero extra scroll margin so an already visible row does not jump. No command-state, cooldown, permission or confirmation rule is bypassed.
- The main window permits a600-logical-pixel minimum height; the1100px minimum width is unchanged. Its preferred startup size is bounded by the current Qt available screen and native title/frame metrics. Gauge/card proportions remain controlled by the existing layouts and their own measurement scroll area. No fixed panel coordinates, widget reconstruction, Windows display-setting changes or data-acquisition changes were introduced.
- Compact Monitor feedback still has its existing56px reserved height. Detailed results remain in Diagnostics with the existing fixed250px card and internal scroll area.

The corrected laptop reproduction has a376px command-row viewport and436px minimum row content, requiring60px of deliberate scrolling. Clicking ACK leaves the scroll offset at0; ACK and CAL LOCK retain their initial coordinates. The panel heading does not scroll. Small-height windowed operation uses the same fallback.

## Automated screen matrix

The tests use Qt6.8's [configurable offscreen screen plugin](https://raw.githubusercontent.com/qt/qtbase/6.8/src/plugins/platforms/offscreen/qoffscreenintegration.cpp), native screen dimensions and fractional QT_SCALE_FACTOR, without changing Windows settings. Each subprocess validates its actual QScreen geometry/DPR. A60-physical-pixel taskbar allowance makes the work area conservative. Each scenario covers LEL670, LEL700, BTU and FID, dark/light, and windowed/maximized/restored states: **96 cases** across four pytest screen tests.

| Physical desktop | Scale | Qt usable logical desktop | Maximized dark670 row viewport | Scroll needed |
|---|---:|---|---:|---|
|1920×1080|100%|1920×1020|715px|No|
|1920×1080|125%|1536×816|512px|No|
|1920×1080|150%|1280×680|376px|Yes,60px; CAL LOCK reachable|
|2560×1440|125%|2048×1104|800px|No|

Assertions cover actual mouse-down/release through the existing confirmation/dispatch path into a stubbed simulation receiver; simultaneous button disabling; acknowledged, verified, unverified, rejected and unknown feedback; long status/results; LED transitions; enabling/disabling; preserved button identities/sizes/positions; panel/header anchoring; independent main-measurement scrolling; scrollbar reachability and keyboard navigation to lower enabled rows. Each process also waits for the real3-second LED timer to expire. No serial transport or real analyzer command is used.

Run `python -m pytest -q tests/test_command_panel_dpi.py`. The confirmed local run passed4 tests in42.69s; reports/screenshots are under tmp/command-dpi-confirmed/. Existing command/layout/locking/theme tests additionally passed92 cases in72.26s. The full regression/package/CI evidence is recorded in PROGRESS.md. This is Qt simulation evidence; manual native-Windows confirmation on the user's specific laptop remains useful.
