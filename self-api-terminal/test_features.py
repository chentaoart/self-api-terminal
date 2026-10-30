# -*- coding: utf-8 -*-
"""新功能的逻辑测试：表格渲染、自定义工具、插件、PDF/Word 附件、参数。

    .venv\\Scripts\\python.exe test_features.py
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("SELFAPI_DATA", os.path.join(os.path.dirname(__file__), ".feattest"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import api  # noqa: E402
import md_render  # noqa: E402
import media  # noqa: E402
import plugins  # noqa: E402
import store  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + str(detail)))
    if not ok:
        FAILS.append(name)


class Echo(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"path": self.path,
                           "header": self.headers.get("X-Test", "")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        body = json.dumps({"got": raw.decode("utf-8", "replace")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    # 1) 表格
    html = md_render.md_to_html("| 名称 | 值 |\n|---|---|\n| a | 1 |\n| b | 2 |")
    check("表格渲染成 table", "<table" in html and "a" in html and "2" in html, html[:120])
    check("表格有表头加粗", "font-weight:700" in html, html[:200])

    # 2) 代码高亮还在
    html = md_render.md_to_html("```python\ndef f():\n    return 1\n```")
    check("代码块仍正常", "Consolas" in html and "def" in html, html[:80])

    # 3) 自定义 HTTP 工具
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    api.set_custom_tools([{
        "name": "echo_api",
        "description": "测试用",
        "method": "GET",
        "url": "http://127.0.0.1:%d/hi?q={input}" % port,
        "headers": "X-Test: yes",
        "input_hint": "随便",
    }])
    schemas = [t["function"]["name"] for t in api.all_tools()]
    check("自定义工具进了 schema", "echo_api" in schemas, schemas)

    out = api.execute_tool("echo_api", json.dumps({"input": "你好"}))
    check("自定义工具能调用", "q=%E4%BD%A0%E5%A5%BD" in out, out[:160])
    check("自定义工具带自定义头", '"yes"' in out, out[:160])

    # 4) 插件
    folder = plugins.plugins_dir()
    (folder / "probe_plugin.py").write_text(
        "def register(reg):\n"
        "    reg.add_tool('plugin_hello', '打个招呼', lambda args: 'hello ' + str(args.get('input','')))\n",
        encoding="utf-8")
    api._PLUGIN_TOOLS.clear()
    ok, bad = plugins.load(api)
    check("插件被加载", "probe_plugin" in ok, (ok, bad))
    out = api.execute_tool("plugin_hello", json.dumps({"input": "world"}))
    check("插件工具能执行", out == "hello world", out)
    (folder / "probe_plugin.py").unlink(missing_ok=True)

    # 5) Word 附件
    try:
        import docx
        doc = docx.Document()
        doc.add_paragraph("第一段：这是 Word 里的内容。")
        doc.add_paragraph("第二段：含中文。")
        path = store.data_dir() / "t.docx"
        doc.save(str(path))
        att = media.add_path(path)
        check("Word 抽文本", att["kind"] == "text" and "第一段" in att["text"], att)
    except Exception as exc:
        check("Word 抽文本", False, exc)

    # 6) PDF 错误要友好（假文件）
    fake = store.data_dir() / "bad.pdf"
    fake.write_bytes(b"%PDF-1.4 not really a pdf")
    try:
        media.add_path(fake)
        check("坏 PDF 给出错误", False, "居然成功了")
    except Exception as exc:
        check("坏 PDF 给出错误", "PDF" in str(exc), exc)

    # 7) 参数会进 payload
    captured = {}

    class Capture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            captured["body"] = json.loads(self.rfile.read(n) or b"{}")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"data: [DONE]\n\n")

    srv2 = ThreadingHTTPServer(("127.0.0.1", 0), Capture)
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    cfg = {"baseUrl": "http://127.0.0.1:%d/v1" % srv2.server_address[1],
           "apiKey": "k", "model": "m"}
    streamer = api.Streamer(cfg, [{"role": "user", "content": "hi"}], lambda *a: None,
                            {"temperature": 0.3, "max_tokens": 128})
    try:
        streamer.run()
    except Exception as exc:
        check("参数请求成功", False, exc)
    body = captured.get("body") or {}
    check("temperature 传了", body.get("temperature") == 0.3, body.get("temperature"))
    check("max_tokens 传了", body.get("max_tokens") == 128, body.get("max_tokens"))
    check("工具 schema 一起发", isinstance(body.get("tools"), list) and len(body["tools"]) >= 3,
          len(body.get("tools") or []))

    srv.shutdown()
    srv2.shutdown()
    print()
    print(("失败 %d 项：" % len(FAILS)) + ", ".join(FAILS) if FAILS else "全部通过")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
