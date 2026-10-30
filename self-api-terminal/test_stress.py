# -*- coding: utf-8 -*-
"""压测最可能崩的几个控件：预览窗口、朗读、看图。

    .venv\\Scripts\\python.exe test_stress.py preview
    .venv\\Scripts\\python.exe test_stress.py tts
    .venv\\Scripts\\python.exe test_stress.py image
"""
import os
import sys
import time

os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".stress"))
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402
import media  # noqa: E402
import store  # noqa: E402
import widgets  # noqa: E402

HTML = "<html><body><h1>hello</h1><script>for(let i=0;i<10000;i++){}</script></body></html>"


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def stress_preview(app):
    for i in range(15):
        win = widgets.PreviewWindow(HTML, "压测 %d" % i)
        win.load()
        win.show()
        pump(app, 0.05)          # 故意在加载途中关掉
        win.close()
        win.deleteLater()
        pump(app, 0.05)
        print("  preview round", i, "ok")
    print("preview 压测完成")


def stress_tts(app):
    import tts
    engine = tts.Tts()
    print("tts ready =", engine.ready, "error =", engine.error)
    for i in range(10):
        engine.speak("测试第 %d 句" % i)
        pump(app, 0.2)
        engine.stop()
        print("  tts round", i, "ok")
    print("tts 压测完成")


def stress_image(app):
    data = store.data_dir()
    path = data / "big.png"
    pix = QPixmap(2400, 1600)
    pix.fill(QColor("#7c3aed"))
    painter = QPainter(pix)
    painter.end()
    pix.save(str(path))
    att = media.add_path(path)
    for i in range(10):
        viewer = widgets.ImageViewer(att)
        viewer.show()
        pump(app, 0.05)
        viewer.close()
        viewer.deleteLater()
        pump(app, 0.05)
        thumb = widgets.ImageThumb(att)
        thumb._open()
        print("  image round", i, "ok")
    print("image 压测完成")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(appmod.theme.QSS)
    if mode == "preview":
        stress_preview(app)
    elif mode == "tts":
        stress_tts(app)
    elif mode == "image":
        stress_image(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
