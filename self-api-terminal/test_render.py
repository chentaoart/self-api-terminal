# -*- coding: utf-8 -*-
"""渲染回归测试：把真实内容（含引用块、表格、代码、中文、百分号）全部过一遍。

    .venv\\Scripts\\python.exe test_render.py [store.json 路径]
"""
import json
import os
import sys

os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".rendertest"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import md_render  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + str(detail)[:200]))
    if not ok:
        FAILS.append(name)


CASES = {
    "引用块（曾经崩在这）": "> 这句话是引用\n> 第二行 100% 确定\n\n后面还有正文",
    "引用带百分号": "> 完成度 80%、成功率 99.9%",
    "表格": "| 名称 | 值 |\n|---|---|\n| a | 1 |\n| b | 2 |",
    "表格带百分号": "| 项目 | 占比 |\n|---|---|\n| 甲 | 80% |\n| 乙 | 20% |",
    "代码块": "```python\ndef f(x):\n    return x * 100  # 100%\n```",
    "代码里有百分号格式串": '```c\nprintf("%d%%\\n", 100);\n```',
    "行内代码": "用 `width=\"100%\"` 这样写",
    "标题+列表": "# 标题\n\n- 一\n- 二\n\n1. 甲\n2. 乙",
    "链接": "见 https://example.com/a?b=1&c=2",
    "粗斜体删除线": "**粗** *斜* ~~删~~ `代码`",
    "空内容": "",
    "只有空白": "   \n\n  \n",
    "很长的一段": "长" * 3000,
    "未闭合代码块": "```python\n没有结束的代码块",
    "奇怪的标记": "| 只有一个竖线\n> 引用里套 | 表格符号\n%%%",
}


def main():
    for name, text in CASES.items():
        try:
            html = md_render.md_to_html(text)
            check("渲染 " + name, isinstance(html, str))
        except Exception as exc:
            check("渲染 " + name, False, "%s: %s" % (type(exc).__name__, exc))

    # 引用块确实渲染成带左边线的块
    html = md_render.md_to_html("> 引用测试")
    check("引用块有样式", "border-left" in html, html[:120])

    # 用户的真实数据（如果能读到）
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if path and os.path.isfile(path):
        try:
            data = json.loads(open(path, encoding="utf-8").read())
            total = bad = 0
            for session in data.get("sessions") or []:
                for msg in session.get("messages") or []:
                    content = msg.get("content")
                    if not isinstance(content, str) or not content.strip():
                        continue
                    total += 1
                    try:
                        md_render.md_to_html(content)
                    except Exception as exc:
                        bad += 1
                        print("    渲染失败：%s" % exc)
                        print("    内容开头：%r" % content[:120])
            check("真实历史全部能渲染 (%d 条)" % total, bad == 0, "%d 条失败" % bad)
        except Exception as exc:
            check("读取真实历史", False, exc)

    print()
    print(("失败 %d 项：" % len(FAILS)) + ", ".join(FAILS) if FAILS else "全部通过")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
