# -*- coding: utf-8 -*-
"""假模型服务：验证流式、工具回合、图片附件。

    python fake_model.py 18899            # 独立跑
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPLY = ("你好，我是测试模型。这条回答分五段流式返回，"
         "用来验证原生窗口的流式渲染、Markdown 排版和代码块。\n\n"
         "```html\n<div style=\"padding:12px;background:#222;color:#fff\">"
         "点“运行”能看到这个预览</div>\n```\n\n"
         "```python\ndef hello(name):\n    # 示例\n    return f\"你好，{name}\"\n```\n\n"
         "结束。")

LOG_PATH = None


def note(msg):
    if not LOG_PATH:
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        out = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._json({"object": "list", "data": [{"id": "fake-model"}, {"id": "fake-reasoner"}]})
            return
        self._json({"ok": True})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        try:
            req = json.loads(raw or b"{}")
        except Exception:
            req = {}

        images, texts, system = 0, 0, ""
        for msg in req.get("messages") or []:
            content = msg.get("content")
            if msg.get("role") == "system":
                system = str(content)[:40]
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "image_url":
                        images += 1
                    elif part.get("type") == "text":
                        texts += 1
            elif isinstance(content, str) and content:
                texts += 1
        note("POST %s stream=%s images=%d texts=%d system=%r" % (
            self.path, bool(req.get("stream")), images, texts, system))

        if not req.get("stream"):
            self._json({"choices": [{"message": {"role": "assistant", "content": "pong"}}]})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def send(obj):
            chunk = "data: " + (obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)) + "\n\n"
            self.wfile.write(chunk.encode("utf-8"))
            self.wfile.flush()

        for think in ("先看条件，", "再决定怎么写。"):
            send({"choices": [{"delta": {"reasoning_content": think}}]})
            time.sleep(0.1)
        parts = [REPLY[i:i + 16] for i in range(0, len(REPLY), 16)]
        for part in parts:
            send({"choices": [{"delta": {"content": part}}]})
            time.sleep(0.05)
        send("[DONE]")


class Server(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True


def serve(port: int, log_path: str = None):
    global LOG_PATH
    LOG_PATH = log_path
    srv = Server(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18899
    log = sys.argv[2] if len(sys.argv) > 2 else None
    print("fake model on http://127.0.0.1:%d/v1" % port, flush=True)
    serve(port, log)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
