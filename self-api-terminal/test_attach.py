# -*- coding: utf-8 -*-
"""附件链路检查：文件 → 消息 → 接口 payload。"""
import base64
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".attachtest"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import api
import media
import store  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else ("  <- " + str(detail))))
    if not ok:
        FAILS.append(name)


# 1x1 红点 PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def main():
    tmp = store.data_dir()
    img_path = tmp / "t.png"
    img_path.write_bytes(PNG)
    txt_path = tmp / "hello.py"
    txt_path.write_text("print('hi')\n", encoding="utf-8")

    img = media.add_path(img_path)
    txt = media.add_path(txt_path)
    check("图片识别为 image", img["kind"] == "image", img)
    check("文本识别为 text", txt["kind"] == "text", txt)
    check("图片入库", os.path.isfile(img.get("path", "")), img)
    check("文本内容读入", "print('hi')" in txt.get("text", ""), txt)

    msg = {"role": "user", "content": "看看这两张", "attachments": [img, txt]}
    payload = api.to_api_message(msg)
    parts = payload["content"]
    check("payload 是数组", isinstance(parts, list), type(parts))
    types = [p["type"] for p in parts]
    check("含文本段", "text" in types, types)
    check("含图片段", "image_url" in types, types)
    text_part = next(p for p in parts if p["type"] == "text")
    check("文本里带附件名", "hello.py" in text_part["text"], text_part["text"][:120])
    check("文本里带用户输入", "看看这两张" in text_part["text"], text_part["text"][:120])
    url = next(p for p in parts if p["type"] == "image_url")["image_url"]["url"]
    check("图片是 data URL", url.startswith("data:image/png;base64,"), url[:40])

    plain = api.to_api_message({"role": "user", "content": "只有文字"})
    check("无附件时仍是字符串", isinstance(plain["content"], str), type(plain["content"]))

    tool = api.to_api_message({"role": "tool", "content": "42", "tool_call_id": "c1", "name": "calculator"})
    check("tool 消息结构", tool["tool_call_id"] == "c1" and tool["name"] == "calculator", tool)

    # 图片丢了也不能炸
    broken = dict(img)
    broken["path"] = str(tmp / "nope.png")
    out = api.to_api_message({"role": "user", "content": "x", "attachments": [broken]})
    check("图片丢失时降级", isinstance(out["content"], list), out)

    print()
    print("失败 %d 项" % len(FAILS) if FAILS else "全部通过")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
