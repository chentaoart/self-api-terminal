# -*- coding: utf-8 -*-
"""设置窗口的「测试连接」：服务器接受连接但不回话时，不能把程序卡死或带崩。"""
import os
import socket
import sys
import threading
import time

os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".settingstest"))
if not os.environ.get("SMOKE_VISIBLE"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as appmod  # noqa: E402
import store  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILS.append(name)


def silent_server():
    """接受连接但一直不返回数据——就是最容易把人卡死的服务器。"""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = srv.getsockname()[1]
    held = []

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            held.append(conn)

    threading.Thread(target=loop, daemon=True).start()
    return srv, port, held


def main():
    srv, port, held = silent_server()
    qapp = QApplication([])
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(appmod.theme.QSS)
    win = appmod.MainWindow()
    win.show()

    cfg = win.store.active_config()
    cfg.update({"name": "黑洞", "baseUrl": "http://127.0.0.1:%d/v1" % port,
                "apiKey": "k", "model": "m"})
    win.store.save()

    dlg = appmod.SettingsDialog(win.store, win)
    dlg.show()
    start = time.time()
    dlg._test()
    check("测试连接是异步的（没卡住界面）", time.time() - start < 1.0, time.time() - start)
    check("按钮已禁用，状态是请求中", not dlg.test_btn.isEnabled())

    # 关掉对话框：后台请求必须自己收尾，不能把进程带走
    dlg.close()
    qapp.processEvents()
    time.sleep(0.3)
    qapp.processEvents()
    check("关掉设置窗口后程序还活着", True)

    # 等它自己超时（read timeout 25 秒），期间界面要能处理事件
    deadline = time.time() + 30
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)

    win.close()
    qapp.processEvents()
    appmod.workers.shutdown(2000)
    for conn in held:
        try:
            conn.close()
        except Exception:
            pass
    srv.close()
    print()
    print(("失败 %d 项：" % len(FAILS)) + ", ".join(FAILS) if FAILS else "全部通过")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
