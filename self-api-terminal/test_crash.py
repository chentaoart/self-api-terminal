# -*- coding: utf-8 -*-
"""崩溃复现：回答流式进行时切换话题 / 关窗口。

    .venv\\Scripts\\python.exe test_crash.py           # 离屏
    SMOKE_VISIBLE=1 .venv\\Scripts\\python.exe test_crash.py
"""
import os
import sys
import time

os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".crashtest"))
if not os.environ.get("SMOKE_VISIBLE"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as appmod  # noqa: E402
import fake_model  # noqa: E402
import store  # noqa: E402

PORT = 18903
FAILS = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILS.append(name)


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main():
    server = fake_model.serve(PORT, str(store.data_dir() / "fake.log"))
    qapp = QApplication([])
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(appmod.theme.QSS)
    win = appmod.MainWindow()
    win.show()

    cfg = win.store.active_config()
    cfg.update({"name": "崩溃测试", "baseUrl": "http://127.0.0.1:%d/v1" % PORT,
                "apiKey": "sk-test", "model": "fake-model"})
    win.store.save()
    win.refresh_chip()

    # 1) 流式途中切换话题
    win.composer.setPlainText("第一句")
    win.send()
    pump(qapp, 0.4)
    win.new_session()            # 清空对话区，旧的 bubble 被 deleteLater
    pump(qapp, 2.5)              # 让流继续吐字，看还在不在
    check("流式途中新建话题没崩", True)

    # 2) 流式途中切到另一个已有话题
    win.composer.setPlainText("第二句")
    win.send()
    pump(qapp, 0.4)
    sessions = win.store.state["sessions"]
    win.store.state["activeSessionId"] = sessions[-1]["id"]
    win.refresh_sessions()
    win.render_session()
    pump(qapp, 2.5)
    check("流式途中切换话题没崩", True)

    # 3) 流式途中关闭窗口
    win.composer.setPlainText("第三句")
    win.send()
    pump(qapp, 0.4)
    win.close()
    pump(qapp, 1.0)
    check("流式途中关窗口没崩", True)

    # 4) 开预览窗口再关主窗口
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
    win2 = appmod.MainWindow()
    win2.show()
    config = win2.store.active_config()
    config.update({"baseUrl": "http://127.0.0.1:%d/v1" % PORT, "model": "fake-model"})
    win2.run_html("<html><body><h1>预览</h1></body></html>", "html")
    pump(qapp, 1.0)
    win2.close()
    pump(qapp, 1.0)
    check("开预览后关窗口没崩", True)

    server.shutdown()
    print()
    print(("失败 %d 项：" % len(FAILS)) + ", ".join(FAILS) if FAILS else "全部通过")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
