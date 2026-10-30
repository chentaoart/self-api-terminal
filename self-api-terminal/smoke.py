# -*- coding: utf-8 -*-
"""离屏冒烟测试：搭出真窗口，带图片+文件+技能发一轮消息，最后截图。

    $env:SELFAPI_DATA='...\\.testdata'; .venv\\Scripts\\python.exe smoke.py shot.png
设 SMOKE_VISIBLE=1 用真实窗口（字体会正常，但会闪一下窗口）。
"""
import base64
import os
import sys
import time

os.environ.setdefault("SELFAPI_DATA", str(os.path.join(os.path.dirname(__file__), ".testdata")))
if not os.environ.get("SMOKE_VISIBLE"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as appmod  # noqa: E402
import dialogs  # noqa: E402
import fake_model  # noqa: E402
import media  # noqa: E402
import store  # noqa: E402

SHOT = sys.argv[1] if len(sys.argv) > 1 else "smoke.png"
PORT = 18901
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def main():
    data = store.data_dir()
    log_path = data / "fake.log"
    if log_path.exists():
        log_path.unlink()
    server = fake_model.serve(PORT, str(log_path))

    qapp = QApplication([])
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(appmod.theme.QSS)
    win = appmod.MainWindow()
    win.show()

    cfg = win.store.active_config()
    cfg.update({"name": "冒烟测试", "baseUrl": "http://127.0.0.1:%d/v1" % PORT,
                "apiKey": "sk-test", "model": "fake-model"})
    win.store.state["skills"] = dialogs.DEFAULT_SKILLS[:2]
    win.store.save()
    win.refresh_chip()
    win._refresh_skills()
    win._toggle_skill(dialogs.DEFAULT_SKILLS[0])
    qapp.processEvents()

    img_path = data / "demo.png"
    img_path.write_bytes(PNG)
    txt_path = data / "demo.py"
    txt_path.write_text("print('hello from attachment')\n", encoding="utf-8")
    win.attachments = [media.add_path(img_path), media.add_path(txt_path)]
    win._refresh_attachments()
    qapp.processEvents()

    empty_shot = SHOT.replace(".png", "-empty.png")
    win.grab().save(empty_shot)

    win.composer.setPlainText("你好，带一张图和一份文件")
    win.send()

    deadline = time.time() + 25
    while time.time() < deadline:
        qapp.processEvents()
        if win.thread is None and win.bubble is None:
            break
        time.sleep(0.05)
    qapp.processEvents()
    time.sleep(0.4)
    qapp.processEvents()

    session = win.store.active_session()
    text = ""
    for msg in session["messages"]:
        if msg.get("role") == "assistant":
            text = msg.get("content") or ""
    sent = session["messages"][0] if session["messages"] else {}

    shot = SHOT
    pix = win.grab()
    pix.save(shot)
    print("回答 =", repr(text[:80]))
    print("首条消息带附件 =", len(sent.get("attachments") or []), "带技能 =", sent.get("skill"))
    print("服务端日志 =", log_path.read_text(encoding="utf-8").strip().splitlines()[-1:]
          if log_path.exists() else "无")
    print("截图 =", shot, pix.width(), "x", pix.height())

    server.shutdown()
    ok_text = "测试模型" in text
    ok_attach = len(sent.get("attachments") or []) == 2
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    ok_image = "images=1" in log
    print("结果 =", "通过" if (ok_text and ok_attach and ok_image) else "失败",
          "(文本=%s 附件=%s 图片到达=%s)" % (ok_text, ok_attach, ok_image))
    return 0 if (ok_text and ok_attach and ok_image) else 1


if __name__ == "__main__":
    raise SystemExit(main())
