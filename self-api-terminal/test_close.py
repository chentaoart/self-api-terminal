# -*- coding: utf-8 -*-
"""最小复现：渲染几个气泡后关窗口，看会不会崩。"""
import os
import sys
import time

os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".closetest2"))
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as appmod  # noqa: E402


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main():
    qapp = QApplication([])
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(appmod.theme.QSS)
    win = appmod.MainWindow()
    win.show()
    print("  .. 窗口好了")

    if os.environ.get("STREAM"):
        import fake_model
        port = 18907
        server = fake_model.serve(port, str(appmod.store.data_dir() / "fake.log"))
        cfg = win.store.active_config()
        cfg.update({"name": "x", "baseUrl": "http://127.0.0.1:%d/v1" % port,
                    "apiKey": "k", "model": "fake-model"})
        win.store.save()
        win.refresh_chip()
        win.composer.setPlainText("来一段")
        win.send()
        end = time.time() + 20
        while time.time() < end and (win.thread is not None or win.bubble is not None):
            qapp.processEvents()
            time.sleep(0.03)
        print("  .. 流完了")

    win.store.active_session()["messages"] = [
        {"role": "user", "content": "问题一"},
        {"role": "assistant", "content": "回答一\n\n> 引用一下 100%\n\n| a | b |\n|---|---|\n| 1 | 2 |"},
        {"role": "user", "content": "问题二"},
        {"role": "assistant", "content": "第二版", "variants": [
            {"content": "第一版", "reasoning": ""},
            {"content": "第二版", "reasoning": "想了想"}], "active": 1},
    ]
    win.render_session()
    pump(qapp, 0.4)
    print("  .. 渲染好了")

    win.close()
    print("  .. 关了")
    for i in range(8):
        qapp.processEvents()
        time.sleep(0.05)
        print("     tick", i, flush=True)
    print("  .. 空转完成")
    appmod.workers.shutdown(1000)
    print("  .. 全部完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
