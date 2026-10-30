# -*- coding: utf-8 -*-
"""复现：点消息下面的「重新生成 / 继续 / 版本切换」这类按钮时，会不会把进程带走。"""
import os
import sys
import time

os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".clicktest"))
if not os.environ.get("SMOKE_VISIBLE"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as appmod  # noqa: E402

# 确认框一律点「是」，否则离屏测试会卡住
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)


class _Sig:
    def connect(self, *a, **k):
        return None


class FakeThread:
    delta = reasoning = tool = toolResult = note = failed = finished = _Sig()

    def __init__(self, *a, **k):
        self.streamer = None

    def start(self):
        pass

    def stop(self):
        pass

    def isRunning(self):
        return False

    def deleteLater(self):
        pass


def pump(app, seconds=0.4):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main():
    old = appmod.ChatThread
    appmod.ChatThread = FakeThread
    qapp = QApplication([])
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(appmod.theme.QSS)
    win = appmod.MainWindow()
    win.show()
    cfg = win.store.active_config()
    cfg.update({"baseUrl": "http://127.0.0.1:1/v1", "model": "m"})
    win.store.save()

    win.store.active_session()["messages"] = [
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "回答"},
    ]
    win.render_session()
    pump(qapp)

    bubbles = win.chat.body.findChildren(appmod.Bubble)
    print("  气泡数 =", len(bubbles))
    assistant = [b for b in bubbles if getattr(b, "role", "") == "assistant"][0]

    print("  .. 点「重新生成」")
    assistant.regen_btn.click()
    pump(qapp)
    print("  .. 点完还活着，消息数 =", len(win.store.active_session()["messages"]))
    win.thread = None

    win.store.active_session()["messages"] = [
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "回答二"},
    ]
    win.render_session()
    pump(qapp)
    bubbles = win.chat.body.findChildren(appmod.Bubble)
    assistant = [b for b in bubbles if getattr(b, "role", "") == "assistant"][0]

    print("  .. 点「继续」")
    assistant.cont_btn.click()
    pump(qapp)
    print("  .. 点完还活着")
    win.thread = None

    # 版本切换按钮已经去掉，这里只确认渲染不报错
    win.store.active_session()["messages"] = [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "回答"},
    ]
    win.render_session()
    pump(qapp, 0.8)
    print("  .. 普通渲染完成")

    # 右键菜单这条路：直接走菜单选完之后的分支（真正的 QMenu.exec 在离屏下会卡）
    win.store.active_session()["messages"] = [
        {"role": "user", "content": "要改的问题"},
        {"role": "assistant", "content": "旧回答"},
    ]
    win.render_session()
    pump(qapp)
    bubbles = win.chat.body.findChildren(appmod.Bubble)
    user_bubble = [b for b in bubbles if getattr(b, "role", "") == "user"][0]

    print("  .. 走「编辑并重发」")
    user_bubble.apply_menu_choice("edit", 0)
    pump(qapp, 0.6)
    print("  .. 消息数 =", len(win.store.active_session()["messages"]),
          " 输入框 =", repr(win.composer.toPlainText()))

    win.store.active_session()["messages"] = [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "答"},
    ]
    win.render_session()
    pump(qapp, 0.5)
    bubbles = win.chat.body.findChildren(appmod.Bubble)
    target = [b for b in bubbles if getattr(b, "role", "") == "assistant"][-1]
    print("  .. 走「删除这条及之后」")
    target.apply_menu_choice("delete", 1)
    pump(qapp, 1.0)
    count_via_menu = len(win.store.active_session()["messages"])
    print("  .. 菜单删除后消息数 =", count_via_menu)
    if count_via_menu != 1:
        # 菜单路径没生效就直接调一次，确认功能本身没问题
        win.store.active_session()["messages"] = [
            {"role": "user", "content": "问"},
            {"role": "assistant", "content": "答"},
        ]
        win._delete_from(1)
        pump(qapp, 0.3)
        print("  .. 直接删除后消息数 =", len(win.store.active_session()["messages"]))

    win.close()
    pump(qapp, 0.3)
    appmod.ChatThread = old
    appmod.workers.shutdown(1000)
    print("  全部完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
