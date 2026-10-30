# -*- coding: utf-8 -*-
"""OpenAI 兼容接口的客户端：流式对话、工具回合、模型列表、连通性测试。

原生程序不需要什么反向代理：请求由本进程直接发出，不带 Origin 头，
所以那些「看到 Origin 就 403」的本地服务也能直接用。
"""

import ast
import base64
import datetime
import html
import http.client
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import media

CONNECT_TIMEOUT = 20.0
READ_TIMEOUT = 600.0
MAX_TOOL_ROUNDS = 5

# 用户自定义的 HTTP 工具（由界面设置，发送前注入）
_CUSTOM_TOOLS: list[dict] = []
# 插件注册的 Python 工具
_PLUGIN_TOOLS: list[dict] = []


def set_custom_tools(tools):
    global _CUSTOM_TOOLS
    _CUSTOM_TOOLS = [t for t in (tools or []) if t.get("name")]


def register_plugin_tool(schema: dict, fn):
    _PLUGIN_TOOLS.append({"schema": schema, "fn": fn})


def custom_tool_schemas():
    out = []
    for tool in _CUSTOM_TOOLS:
        out.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description") or tool["name"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": tool.get("input_hint") or "传给这个工具的内容",
                        }
                    },
                    "required": ["input"],
                },
            },
        })
    return out


def all_tools():
    return TOOLS + custom_tool_schemas() + [p["schema"] for p in _PLUGIN_TOOLS]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算一个数学表达式，支持 + - * / ** 括号和 sin/cos/log 等函数。",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "要计算的表达式"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取指定时区的当前时间，例如 Asia/Shanghai。",
            "parameters": {
                "type": "object",
                "properties": {"timezone": {"type": "string", "description": "IANA 时区名"}},
                "required": ["timezone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "抓取一个网页并返回纯文本内容。",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "http/https 链接"}},
                "required": ["url"],
            },
        },
    },
]


class ApiError(Exception):
    pass


def to_api_message(msg: dict) -> dict:
    """把界面里的消息（可能带附件）转成 OpenAI 接口要的形状。"""
    role = msg.get("role")
    if role == "tool":
        out = {"role": "tool", "tool_call_id": msg.get("tool_call_id") or "",
               "content": msg.get("content") or ""}
        if msg.get("name"):
            out["name"] = msg["name"]
        return out
    if role == "assistant":
        out = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            out["tool_calls"] = msg["tool_calls"]
        return out

    text = msg.get("content") or ""
    atts = msg.get("attachments") or []
    if not atts:
        return {"role": role or "user", "content": text}

    blocks, images = [], []
    for att in atts:
        kind = att.get("kind")
        if kind == "text":
            blocks.append("【附件：%s】\n```\n%s\n```" % (att.get("name") or "文件",
                                                        att.get("text") or ""))
        elif kind == "image":
            images.append(att)

    parts = []
    joined = "\n\n".join(blocks)
    if joined and text:
        joined = joined + "\n\n" + text
    elif text and not joined:
        joined = text
    if joined:
        parts.append({"type": "text", "text": joined})
    for att in images:
        try:
            parts.append({"type": "image_url", "image_url": {"url": media.data_url(att)}})
        except Exception:
            continue
    if not parts:
        parts = [{"type": "text", "text": text or "（空消息）"}]
    return {"role": role or "user", "content": parts}


# ---------------------------------------------------------------- 连接


def _split_base(base_url: str):
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ApiError("还没有填 Base URL")
    p = urllib.parse.urlsplit(base)
    if p.scheme not in ("http", "https"):
        raise ApiError("Base URL 要以 http:// 或 https:// 开头")
    if not p.hostname:
        raise ApiError("Base URL 缺少主机名")
    port = p.port or (443 if p.scheme == "https" else 80)
    return p.scheme, p.hostname, port, p.path.rstrip("/")


def _connect(cfg: dict, timeout: float = CONNECT_TIMEOUT, read_timeout: float | None = None):
    scheme, host, port, prefix = _split_base(cfg.get("baseUrl", ""))
    cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
    conn = cls(host, port, timeout=timeout)
    conn.connect()
    try:
        conn.sock.settimeout(read_timeout or READ_TIMEOUT)
    except Exception:
        pass
    return conn, prefix


def _headers(cfg: dict) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = (cfg.get("apiKey") or "").strip()
    if key:
        headers["Authorization"] = "Bearer " + key
    return headers


# ---------------------------------------------------------------- 流式对话


class Streamer:
    """一次对话（含工具回合）的执行体，可被别的线程 cancel()。"""

    def __init__(self, cfg, messages, emit, params=None):
        self.cfg = cfg
        self.messages = messages          # 会被就地追加（工具回合）
        self.emit = emit                  # emit(event, *payload)
        self.params = params or {}        # temperature / top_p / max_tokens
        self._cancel = False
        self._conn = None

    def cancel(self):
        self._cancel = True
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass

    @property
    def cancelled(self) -> bool:
        return self._cancel

    # -------------------------------------------------------------- 主体

    def run(self):
        model = (self.cfg.get("model") or "").strip()
        if not model:
            raise ApiError("还没有填模型名")
        for _round in range(MAX_TOOL_ROUNDS):
            if self._cancel:
                return
            content, reasoning, calls, finish = self._one_round(model)
            if self._cancel:
                return
            if not calls:
                return
            self.messages.append({
                "role": "assistant",
                "content": content or "",
                "reasoning": reasoning or "",
                "tool_calls": calls,
            })
            for call in calls:
                name = call.get("function", {}).get("name", "")
                args = call.get("function", {}).get("arguments", "") or ""
                self.emit("tool", name, args)
                result = execute_tool(name, args)
                self.emit("tool_result", name, result)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or "",
                    "name": name,
                    "content": result,
                })
        self.emit("note", "工具调用达到上限，先停下来。")

    def _one_round(self, model):
        payload = {
            "model": model,
            "messages": [to_api_message(m) for m in self.messages],
            "tools": all_tools(),
            "tool_choice": "auto",
            "stream": True,
        }
        for key in ("temperature", "top_p", "max_tokens"):
            value = self.params.get(key)
            if value not in (None, "", 0):
                payload[key] = value
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            conn, prefix = _connect(self.cfg)
        except (OSError, ApiError) as exc:
            raise ApiError("连不上 %s：%s" % (self.cfg.get("baseUrl"), exc))

        self._conn = conn
        try:
            conn.request("POST", prefix + "/chat/completions", body=body, headers=_headers(self.cfg))
            resp = conn.getresponse()
            if resp.status != 200:
                detail = resp.read().decode("utf-8", "replace")
                raise ApiError("API 返回 %d\n%s" % (resp.status, detail[:900]))
            return self._consume(resp)
        finally:
            self._conn = None
            try:
                conn.close()
            except Exception:
                pass

    def _consume(self, resp):
        content = []
        reasoning = []
        calls = {}          # index -> {id,type,function{name,arguments}}
        finish = None
        try:
            while not self._cancel:
                line = resp.readline()
                if not line:
                    break
                line = line.strip()
                if not line or not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    break
                try:
                    chunk = json.loads(payload.decode("utf-8", "replace"))
                except Exception:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
                delta = choice.get("delta") or choice.get("message") or {}
                think = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thinking")
                if think:
                    reasoning.append(think)
                    self.emit("reasoning", think)
                text = delta.get("content")
                if text:
                    content.append(text)
                    self.emit("delta", text)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index")
                    if idx is None:
                        idx = len(calls)
                    slot = calls.setdefault(idx, {"id": "", "type": "function",
                                                  "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]
        except (OSError, http.client.HTTPException) as exc:
            if not self._cancel:
                raise ApiError("连接中断：%s" % exc)
        return ("".join(content), "".join(reasoning),
                [calls[i] for i in sorted(calls)], finish)


# ---------------------------------------------------------------- 其它接口


def fetch_context_limit(cfg: dict) -> tuple[int | None, str]:
    """问 llama.cpp 的 /props 要 n_ctx；不是 llama.cpp 就返回 (None, 原因)。"""
    base = (cfg.get("baseUrl") or "").strip().rstrip("/")
    if not base:
        return None, "没有 Base URL"
    root = base[:-3] if base.endswith("/v1") else base
    for path in ("/props", "/v1/props"):
        try:
            req = urllib.request.Request(root + path, headers=_headers(cfg))
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        settings = data.get("default_generation_settings") or {}
        for value in (settings.get("n_ctx"), data.get("n_ctx"),
                      settings.get("params", {}).get("n_ctx")):
            if isinstance(value, int) and value > 0:
                return value, "llama.cpp /props"
        if data.get("model_path") or data.get("n_ctx") is not None:
            return None, "接口是 llama.cpp，但没给出 n_ctx"
    return None, "这个接口不提供上下文长度（只有 llama.cpp 的 /props 会给）"


def list_models(cfg: dict) -> list[str]:
    conn, prefix = _connect(cfg, timeout=10, read_timeout=20)
    try:
        headers = _headers(cfg)
        headers["Accept"] = "application/json"
        conn.request("GET", prefix + "/models", headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        if resp.status != 200:
            raise ApiError("HTTP %d\n%s" % (resp.status, raw[:500]))
        data = json.loads(raw)
        items = data.get("data") if isinstance(data, dict) else None
        ids = []
        for it in items or []:
            if isinstance(it, dict) and it.get("id"):
                ids.append(str(it["id"]))
            elif isinstance(it, str):
                ids.append(it)
        return ids
    finally:
        try:
            conn.close()
        except Exception:
            pass


def test_connection(cfg: dict) -> tuple[bool, str]:
    model = (cfg.get("model") or "").strip()
    if not model:
        return False, "请先填模型名"
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "ping"}],
                       "max_tokens": 1, "stream": False}).encode("utf-8")
    try:
        conn, prefix = _connect(cfg, timeout=10, read_timeout=25)
    except Exception as exc:
        return False, "连不上：%s" % exc
    try:
        conn.request("POST", prefix + "/chat/completions", body=body, headers=_headers(cfg))
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        if resp.status == 200:
            return True, "连接成功"
        return False, "HTTP %d：%s" % (resp.status, raw.strip().replace("\n", " ")[:160])
    except Exception as exc:
        return False, "请求失败：%s" % exc
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------- 工具


def execute_tool(name: str, args_json: str) -> str:
    try:
        args = json.loads(args_json) if args_json and args_json.strip() else {}
    except Exception:
        return "错误：工具参数不是合法 JSON"
    if not isinstance(args, dict):
        return "错误：工具参数必须是对象"
    try:
        if name == "calculator":
            return _calculator(str(args.get("expression", "")))
        if name == "get_current_time":
            return _current_time(str(args.get("timezone", "UTC")))
        if name == "fetch_url":
            return _fetch_url(str(args.get("url", "")))
        custom = next((t for t in _CUSTOM_TOOLS if t.get("name") == name), None)
        if custom is not None:
            return _call_custom_tool(custom, str(args.get("input", "")))
        plugin = next((p for p in _PLUGIN_TOOLS
                       if p["schema"]["function"]["name"] == name), None)
        if plugin is not None:
            result = plugin["fn"](args)
            if isinstance(result, str):
                return result[:8000]
            return json.dumps(result, ensure_ascii=False)[:8000]
        return "错误：未知工具 %s" % name
    except Exception as exc:
        return "错误：%s" % exc


def _call_custom_tool(tool: dict, value: str) -> str:
    url = (tool.get("url") or "").replace("{input}", urllib.parse.quote(value))
    body_text = (tool.get("body") or "").replace("{input}", value)
    method = (tool.get("method") or "GET").upper()
    headers = {"User-Agent": "HermesNative/1.0"}
    for line in (tool.get("headers") or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    data = None
    if method not in ("GET", "HEAD") and body_text:
        data = body_text.encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read(300000)
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, "replace")[:8000] or "（工具没有返回内容）"


_ALLOWED_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin,
    "acos": math.acos, "atan": math.atan, "log": math.log, "log2": math.log2,
    "log10": math.log10, "exp": math.exp, "sqrt": math.sqrt, "abs": abs,
    "round": round, "floor": math.floor, "ceil": math.ceil, "min": min, "max": max,
}
_ALLOWED_NAMES = dict(_ALLOWED_FUNCS, pi=math.pi, e=math.e)


def _calculator(expression: str) -> str:
    expr = expression.strip()
    if not expr:
        raise ValueError("表达式为空")
    node = ast.parse(expr, mode="eval")
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if not isinstance(sub.func, ast.Name) or sub.func.id not in _ALLOWED_FUNCS:
                raise ValueError("不允许调用该函数")
            if sub.keywords:
                raise ValueError("不支持关键字参数")
        elif not isinstance(sub, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                                  ast.Name, ast.operator, ast.unaryop, ast.Load,
                                  ast.Tuple, ast.List)):
            raise ValueError("表达式里有不支持的写法")
    value = eval(compile(node, "<calc>", "eval"), {"__builtins__": {}}, _ALLOWED_NAMES)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("结果不是有效数字")
    return str(value)


def _current_time(tz_name: str) -> str:
    tz_name = tz_name.strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        raise ValueError('无效的时区名 "%s"' % tz_name)
    now = datetime.datetime.now(tz)
    weekday = "一二三四五六日"[now.weekday()]
    offset = now.strftime("%z")
    return "%s（%s，UTC%s）\nISO: %s" % (
        now.strftime("%Y-%m-%d %H:%M:%S"), "周" + weekday, offset, now.isoformat())


def _fetch_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("只支持 http/https 链接")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HermesNative/1.0",
        "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read(1500000)
        charset = resp.headers.get_content_charset() or "utf-8"
    text = raw.decode(charset, "replace")
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)</(p|div|section|article|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()
    return text[:12000] or "（页面没有可读文本）"


# ---------------------------------------------------------------- 画图


def generate_image(cfg: dict, prompt: str, size: str = "1024x1024",
                   model: str = "") -> bytes:
    """调用 OpenAI 兼容的 /images/generations，返回 PNG/JPEG 字节。"""
    model = (model or cfg.get("imageModel") or "").strip()
    payload = {"prompt": prompt, "n": 1, "size": size, "response_format": "b64_json"}
    if model:
        payload["model"] = model
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    conn, prefix = _connect(cfg, timeout=30)
    try:
        conn.request("POST", prefix + "/images/generations", body=body,
                     headers=_headers(cfg))
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            raise ApiError("画图接口返回 %d：%s" % (
                resp.status, raw.decode("utf-8", "replace")[:400]))
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            raise ApiError("画图接口返回的不是 JSON")
        items = data.get("data") or []
        if not items:
            raise ApiError("接口没有返回图片")
        item = items[0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            with urllib.request.urlopen(item["url"], timeout=60) as r:
                return r.read(20 * 1024 * 1024)
        raise ApiError("返回里没有 b64_json 也没有 url")
    finally:
        try:
            conn.close()
        except Exception:
            pass
