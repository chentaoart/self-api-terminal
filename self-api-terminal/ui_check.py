# -*- coding: utf-8 -*-
"""检查设置对话框、空状态、渲染等纯界面构造没有问题。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".uicheck"))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as appmod  # noqa: E402

# 关掉所有确认框，避免离屏测试卡在模态对话框上
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

ok = True


def check(name, fn):
    global ok
    try:
        fn()
        print("  ok   ", name)
    except Exception as exc:
        ok = False
        print("  FAIL ", name, "->", type(exc).__name__, exc)


def main():
    qapp = QApplication([])
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(appmod.theme.QSS)
    win = appmod.MainWindow()
    win.show()
    qapp.processEvents()

    check("空状态", lambda: win.chat.show_empty())
    check("新建话题", lambda: (win.new_session(), qapp.processEvents()))
    check("渲染消息", lambda: (
        win.store.active_session()["messages"].extend([
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "# 标题\n\n**粗体** 和 `代码`\n\n- 一\n- 二", "reasoning": "想了想"},
            {"role": "tool", "name": "calculator", "content": "2"},
        ]),
        win.render_session(),
        qapp.processEvents(),
    ))
    check("刷新侧栏", lambda: (win.refresh_sessions(), qapp.processEvents()))
    check("切换配置菜单", lambda: win._activate_cfg(win.store.state["configs"][0]["id"]))

    dlg = appmod.SettingsDialog(win.store, win)
    check("设置对话框构造", lambda: (dlg.show(), qapp.processEvents()))
    check("新增配置", lambda: (dlg._add(), qapp.processEvents()))
    check("删除配置", lambda: (dlg._remove(), qapp.processEvents()))
    check("关闭设置", lambda: (dlg.close(), qapp.processEvents()))

    # 新对话框
    params = appmod.dialogs.ParamsDialog(win.store, win)
    params.f_temp.setText("0.6")
    params.f_topp.setText("0.9")
    params.f_maxtok.setText("1024")
    params.f_system.setPlainText("你是助手")
    check("参数对话框保存", lambda: (params._save(), qapp.processEvents()))
    check("参数真的存了", lambda: win.store.state["params"]["temperature"] == 0.6
          and win.store.state["system"] == "你是助手")

    tools = appmod.dialogs.ToolsDialog(win.store, win)
    check("工具对话框构造", lambda: (tools._add(), qapp.processEvents()))
    tools.f_name.setText("demo")
    tools.f_url.setText("http://127.0.0.1:1/x?q={input}")
    check("工具保存", lambda: (tools._save(), qapp.processEvents()))
    check("工具进了 api", lambda: any(t["function"]["name"] == "demo"
                                   for t in appmod.api.all_tools()))

    compare = appmod.dialogs.CompareDialog(win.store, win)
    check("对比对话框构造", lambda: (compare.show(), qapp.processEvents()))
    check("对比对话框关闭", lambda: (compare.close(), qapp.processEvents()))

    image = appmod.dialogs.ImageDialog(win.store, win)
    check("画图对话框构造", lambda: (image.show(), qapp.processEvents()))
    check("画图对话框关闭", lambda: (image.close(), qapp.processEvents()))

    # 消息编辑 / 删除
    win.store.active_session()["messages"] = [
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "回答一"},
        {"role": "user", "content": "第二句"},
    ]
    win.render_session()
    check("编辑消息", lambda: (win._edit_message(0), qapp.processEvents()))
    check("编辑后只剩输入框内容", lambda: win.composer.toPlainText() == "第一句"
          and len(win.store.active_session()["messages"]) == 0)

    win.store.active_session()["messages"] = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]
    check("删除消息", lambda: (win._delete_from(1), qapp.processEvents()))
    check("删除后只剩一条", lambda: len(win.store.active_session()["messages"]) == 1)

    check("关闭窗口", lambda: (win.close(), qapp.processEvents()))

    # ---------------------------------------------------------- 手感相关
    def expect(cond, msg=""):
        if not cond:
            raise AssertionError(msg or "断言失败")

    win2 = appmod.MainWindow()
    win2.show()
    cfg = win2.store.active_config()
    cfg.update({"baseUrl": "http://127.0.0.1:1/v1", "model": "fake-model"})
    win2.store.save()

    before = len(win2.store.state["sessions"])
    win2.composer.setPlainText("/new")
    win2.send()
    check("指令 /new", lambda: expect(len(win2.store.state["sessions"]) == before + 1,
                                    "%d" % len(win2.store.state["sessions"])))

    win2.store.active_session()["messages"] = [{"role": "user", "content": "字" * 1600}]
    win2._update_ctx()
    check("上下文占用显示", lambda: expect("k" in win2.ctx_label.text(),
                                     win2.ctx_label.text()))

    check("滚动跟随默认开", lambda: expect(win2.chat.is_following()))

    captured = {}

    class _Sig:
        def connect(self, *a, **k):
            return None

    class FakeThread:
        delta = reasoning = tool = toolResult = note = failed = finished = _Sig()

        def __init__(self, cfg, messages, params=None, parent=None):
            captured["messages"] = messages
            self.streamer = None

        def start(self):
            pass

        def stop(self):
            pass

        def isRunning(self):
            return False

        def deleteLater(self):
            pass

    old_thread = appmod.ChatThread
    appmod.ChatThread = FakeThread
    try:
        win2.store.active_session()["system"] = "你是测试人格"
        win2.composer.setPlainText("你好")
        win2.send()
    finally:
        appmod.ChatThread = old_thread
        win2.thread = None
    check("话题系统提示词进请求",
          lambda: expect(bool(captured.get("messages"))
                         and captured["messages"][0]["content"] == "你是测试人格",
                         (captured.get("messages") or [])[:1]))

    # 重新生成：只带历史，不把旧回答当上下文
    win2.store.active_session()["messages"] = [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "旧回答"},
    ]
    captured.clear()
    appmod.ChatThread = FakeThread
    try:
        win2._regenerate(1)
    finally:
        appmod.ChatThread = old_thread
        win2.thread = None
    check("重新生成只带历史", lambda: (
        expect(bool(captured.get("messages"))),
        expect(not any(m.get("role") == "assistant" for m in captured["messages"])),
        expect(captured["messages"][-1]["content"] == "问"),
        expect(len(win2.store.active_session()["messages"]) == 1)))

    # 参数：上下文上限 + 预设
    params2 = appmod.dialogs.ParamsDialog(win2.store, win2)
    params2.f_ctx.setText("16384")
    check("手填上下文上限", lambda: (
        params2._save(),
        expect(win2.store.state["contextLimit"] == 16384),
        expect(win2.store.state["contextLimitAuto"] is False)))

    win2.store.state["contextLimitAuto"] = True
    win2._on_ctx_detected((32768, "测试"))
    check("自动检测上下文生效", lambda: expect(win2.store.state["contextLimit"] == 32768))

    # 上下文用量的显示与裁剪
    win2.store.state["contextLimit"] = 1000
    win2.store.state["contextLimitAuto"] = False
    win2.store.active_session()["messages"] = [
        {"role": "user", "content": "旧" * 800},
        {"role": "assistant", "content": "旧答" * 400},
        {"role": "user", "content": "新问题"},
        {"role": "assistant", "content": "新回答"},
    ]
    win2._update_ctx()
    check("超限显示百分比", lambda: expect("/" in win2.ctx_label.text()
                                       and "%" in win2.ctx_label.text(),
                                       win2.ctx_label.text()))
    check("超限变红", lambda: expect("ef4444" in win2.ctx_label.styleSheet(),
                                 win2.ctx_label.styleSheet()))
    check("裁剪后变小", lambda: (win2._trim_context(),
                              expect(win2._estimate_tokens() <= 700)))
    check("裁剪后第一条是用户",
          lambda: expect(win2.store.active_session()["messages"][0].get("role") == "user"))
    check("没超限就不拦", lambda: expect(win2._check_context(10)))

    win2.close()
    qapp.processEvents()

    appmod.workers.shutdown(1500)

    print("结果 =", "通过" if ok else "失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
