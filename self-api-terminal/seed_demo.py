# -*- coding: utf-8 -*-
"""造一份演示数据（技能 + 带图提问 + 含 HTML 的回答），用来截图。"""
import os
import sys

TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), ".demo")
os.environ["SELFAPI_DATA"] = TARGET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter  # noqa: E402

import dialogs  # noqa: E402
import media  # noqa: E402
import store  # noqa: E402


def make_image(path):
    img = QImage(560, 340, QImage.Format_RGB32)
    grad = QLinearGradient(0, 0, 560, 340)
    grad.setColorAt(0.0, QColor("#7c3aed"))
    grad.setColorAt(1.0, QColor("#c026d3"))
    painter = QPainter(img)
    painter.fillRect(img.rect(), grad)
    painter.setPen(QColor("#ffffff"))
    font = painter.font()
    font.setPointSize(28)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(img.rect(), Qt.AlignCenter, "示例图片")
    painter.end()
    img.save(path)


def main():
    os.makedirs(TARGET, exist_ok=True)
    _app = QGuiApplication([])          # QPainter 画文字需要
    img_path = os.path.join(TARGET, "demo.png")
    make_image(img_path)

    st = store.Store()
    st.state["skills"] = [dict(s) for s in dialogs.DEFAULT_SKILLS]
    cfg = st.active_config()
    cfg.update({"name": "本地模型", "providerId": "custom",
                "baseUrl": "http://127.0.0.1:9000/v1", "apiKey": "sk-local",
                "model": "qwen3.8-flash-next-q2_0"})

    session = st.active_session()
    session["title"] = "看图 + 运行预览"
    image = media.add_path(img_path)
    session["messages"] = [
        {"role": "user", "content": "这张图配一段能跑的小页面，说明一下配色。",
         "attachments": [image],
         "skill": {"emoji": "🧩", "name": "解释代码"}},
        {"role": "assistant",
         "reasoning": "先看图：主色是紫到洋红的对角渐变；再写一个同样配色的卡片页面。",
         "content": (
             "这张图是**紫 → 洋红**的对角渐变（`#7c3aed` → `#c026d3`），中间是白色标题。\n\n"
             "配色可以直接用在卡片上：\n\n"
             "```html\n<div style=\"padding:24px;border-radius:16px;"
             "background:linear-gradient(135deg,#7c3aed,#c026d3);color:#fff;"
             "font-family:system-ui\">\n"
             "  <h2 style=\"margin:0 0 8px\">示例图片</h2>\n"
             "  <p style=\"margin:0;opacity:.85\">点下面的「运行 HTML」可以看到效果</p>\n"
             "</div>\n```\n\n"
             "要点：\n"
             "1. 渐变角度 135°，两个色标分别落在左上和右下；\n"
             "2. 文字用纯白保证对比度；\n"
             "3. 圆角 16px 和页面整体的卡片风格一致。\n\n"
             "| 用途 | 色值 | 对比度 |\n|---|---|---|\n"
             "| 主色 | `#7c3aed` | 5.1:1 |\n"
             "| 收敛色 | `#c026d3` | 4.8:1 |\n"
             "| 文字 | `#ffffff` | 12.6:1 |")},
    ]
    st.save()
    print("demo store =", st.path)
    print("image =", image["path"])


if __name__ == "__main__":
    main()
