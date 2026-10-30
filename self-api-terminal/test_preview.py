# -*- coding: utf-8 -*-
"""预览窗口自检：用 QtWebEngine 渲染 HTML，取回 DOM 文本并抓真实屏幕截图。"""
import ctypes
import os
import sys
import time

os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".previewtest"))
# 当前开发环境里 Chromium 自带的沙箱起不来，测试时关掉；正式运行不关。
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402
import widgets  # noqa: E402

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>预览测试</title></head>
<body style="background:#111;color:#eee;font-family:sans-serif;padding:24px">
<h1>预览窗口能用</h1>
<p>这段内容由 QtWebEngine 渲染。</p>
<div id="o" style="margin-top:12px;color:#a78bfa">还没点</div>
</body></html>"""


def grab_window(hwnd, out):
    user32 = ctypes.windll.user32
    HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
    SWP = 0x0001 | 0x0002 | 0x0004 | 0x0010
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP)
    time.sleep(0.8)
    screen = QApplication.primaryScreen()
    pix = screen.grabWindow(hwnd)
    pix.save(out)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP)
    return pix


def main():
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(appmod.theme.QSS)

    print("QWebEngineView 可用 =", widgets.load_engine() is not None)
    win = widgets.PreviewWindow(HTML, "网页预览测试")
    win.load()
    win.show()

    if win.view is not None:
        loop = QEventLoop()
        win.view.loadFinished.connect(lambda ok: loop.quit())
        QTimer.singleShot(8000, loop.quit)
        loop.exec()

    time.sleep(0.6)
    for _ in range(30):
        app.processEvents()
        time.sleep(0.05)

    text = None
    if win.view is not None:
        box = {}

        def got(value):
            box["v"] = value

        win.view.page().runJavaScript("document.body.innerText", 0, got)
        for _ in range(40):
            app.processEvents()
            if "v" in box:
                break
            time.sleep(0.05)
        text = box.get("v")
    print("DOM 文本 =", repr(text)[:120])

    pix = grab_window(int(win.winId()), "preview.png")
    print("截图 = preview.png", pix.width(), "x", pix.height())
    win.close()
    ok = bool(text) and "预览窗口能用" in text
    print("结果 =", "通过" if ok else "失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
