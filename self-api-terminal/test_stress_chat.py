# -*- coding: utf-8 -*-
"""连发多轮压力测试：同一进程里连续 5 次请求 + 重新生成 + 继续，最后干净退出。

    .venv\\Scripts\\python.exe test_stress_chat.py
"""
import os
import sys
import time

os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".stresschat"))
if not os.environ.get("SMOKE_VISIBLE"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as appmod  # noqa: E402
import fake_model  # noqa: E402
import store  # noqa: E402

PORT = 18913
FAILS = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILS.append(name)


def wait_done(app, win, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if win.thread is None and win.bubble is None:
            return True
        time.sleep(0.03)
    return False


def main():
    base = os.environ.get("SELFAPI_BASE")
    server = None
    if not base:
        server = fake_model.serve(PORT, str(store.data_dir() / "fake.log"))
        base = "http://127.0.0.1:%d/v1" % PORT
    qapp = QApplication([])
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(appmod.theme.QSS)
    win = appmod.MainWindow()
    win.show()

    cfg = win.store.active_config()
    cfg.update({"name": "压力", "baseUrl": base, "apiKey": "k", "model": "fake-model"})
    win.store.save()
    win.refresh_chip()

    for i in range(5):
        win.composer.setPlainText("第 %d 轮" % (i + 1))
        win.send()
        ok = wait_done(qapp, win)
        check("第 %d 轮完成" % (i + 1), ok)
        if not ok:
            break

    session = win.store.active_session()
    last = len(session["messages"]) - 1
    win._regenerate(last)
    check("重新生成完成", wait_done(qapp, win))

    session = win.store.active_session()
    last = len(session["messages"]) - 1
    win._continue_reply(last)
    check("继续完成", wait_done(qapp, win))

    win.close()
    for _ in range(6):
        qapp.processEvents()
        time.sleep(0.05)
    if server is not None:
        server.shutdown()
    appmod.workers.shutdown(1500)
    print("  .. 回收窗口")
    appmod.workers.purge()
    win.deleteLater()
    for _ in range(8):
        qapp.processEvents()
        time.sleep(0.05)
    print("  .. 退出")
    print()
    print(("失败 %d 项：" % len(FAILS)) + ", ".join(FAILS) if FAILS else "全部通过")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
