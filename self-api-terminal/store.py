# -*- coding: utf-8 -*-
"""本地数据：配置 / 话题 / 设置，存成一个 JSON。"""

import json
import os
import secrets
import sys
import time
from pathlib import Path

APP_NAME = "SelfApiTerminal"
STORE_VERSION = 1

PRESETS = [
    ("openai", "OpenAI", "https://api.openai.com/v1"),
    ("deepseek", "DeepSeek", "https://api.deepseek.com/v1"),
    ("moonshot", "Moonshot", "https://api.moonshot.cn/v1"),
    ("zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4"),
    ("qwen", "通义千问", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("groq", "Groq", "https://api.groq.com/openai/v1"),
    ("openrouter", "OpenRouter", "https://openrouter.ai/api/v1"),
    ("ollama", "Ollama（本机）", "http://localhost:11434/v1"),
    ("custom", "自定义", ""),
]


_DATA_CACHE = {}


def data_dir() -> Path:
    """数据目录，按可写性依次退让，任何情况下都不让程序起不来。"""
    if "p" in _DATA_CACHE:
        return _DATA_CACHE["p"]

    override = os.environ.get("SELFAPI_DATA")
    if override:
        d = Path(override)
        d.mkdir(parents=True, exist_ok=True)
        _DATA_CACHE["p"] = d
        return d

    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    candidates = [
        Path(base) / APP_NAME,
        Path.home() / ("." + APP_NAME.lower()),
        (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
         else Path(__file__).resolve().parent) / "data",
        Path(os.environ.get("TEMP") or ".") / APP_NAME,
    ]
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            _DATA_CACHE["p"] = d
            return d
        except Exception:
            continue
    _DATA_CACHE["p"] = Path(os.environ.get("TEMP") or ".")
    return _DATA_CACHE["p"]


def new_id() -> str:
    return "x" + secrets.token_hex(4)


def now_ms() -> int:
    return int(time.time() * 1000)


def default_config(index: int = 1) -> dict:
    return {
        "id": new_id(),
        "name": "配置 %d" % index,
        "providerId": "custom",
        "baseUrl": "",
        "apiKey": "",
        "model": "",
    }


def default_state() -> dict:
    cfg = default_config(1)
    cfg.update({"name": "新配置", "providerId": "openai",
                "baseUrl": PRESETS[0][2], "model": ""})
    session = {
        "id": new_id(),
        "title": "新话题",
        "pinned": False,
        "createdAt": now_ms(),
        "updatedAt": now_ms(),
        "messages": [],
    }
    return {
        "version": STORE_VERSION,
        "configs": [cfg],
        "activeId": cfg["id"],
        "sessions": [session],
        "activeSessionId": session["id"],
        "thinking": False,
        "geometry": None,
        "skills": [],
        "ttsAuto": False,
        "params": {"temperature": None, "top_p": None, "max_tokens": None},
        "system": "",
        "tools": [],
        "previewExternal": False,
        "contextLimit": 8192,
        "contextLimitAuto": True,
    }


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else data_dir() / "store.json"
        self.state = self._load()

    # ---------------------------------------------------------------- io

    def _load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or "sessions" not in raw:
                raise ValueError("bad store")
            return self._normalize(raw)
        except FileNotFoundError:
            return default_state()
        except Exception:
            # 坏了就备份一份再重建，别让用户丢得不明不白
            try:
                if self.path.exists():
                    self.path.replace(self.path.with_suffix(".broken.json"))
            except Exception:
                pass
            return default_state()

    @staticmethod
    def _normalize(s: dict) -> dict:
        s.setdefault("version", STORE_VERSION)
        s.setdefault("configs", [])
        s.setdefault("sessions", [])
        s.setdefault("thinking", False)
        s.setdefault("geometry", None)
        s.setdefault("skills", [])
        s.setdefault("ttsAuto", False)
        s.setdefault("params", {"temperature": None, "top_p": None, "max_tokens": None})
        s.setdefault("system", "")
        s.setdefault("tools", [])
        s.setdefault("previewExternal", False)
        s.setdefault("contextLimit", 8192)
        s.setdefault("contextLimitAuto", True)
        if not s["configs"]:
            s["configs"] = [default_config(1)]
        if not s["sessions"]:
            s["sessions"] = [{
                "id": new_id(), "title": "新话题", "pinned": False,
                "createdAt": now_ms(), "updatedAt": now_ms(), "messages": [],
            }]
        ids = {c["id"] for c in s["configs"]}
        if s.get("activeId") not in ids:
            s["activeId"] = s["configs"][0]["id"]
        sids = {x["id"] for x in s["sessions"]}
        if s.get("activeSessionId") not in sids:
            s["activeSessionId"] = s["sessions"][0]["id"]
        return s

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------- 查询

    def config(self, cid: str | None = None) -> dict | None:
        cid = cid or self.state["activeId"]
        for c in self.state["configs"]:
            if c["id"] == cid:
                return c
        return None

    def active_config(self) -> dict | None:
        return self.config(self.state["activeId"])

    def session(self, sid: str | None = None) -> dict | None:
        sid = sid or self.state["activeSessionId"]
        for s in self.state["sessions"]:
            if s["id"] == sid:
                return s
        return None

    def active_session(self) -> dict:
        s = self.session()
        if s is None:
            s = self.state["sessions"][0]
            self.state["activeSessionId"] = s["id"]
        return s

    # ------------------------------------------------------------- 修改

    def add_session(self) -> dict:
        s = {
            "id": new_id(),
            "title": "新话题",
            "pinned": False,
            "createdAt": now_ms(),
            "updatedAt": now_ms(),
            "messages": [],
        }
        self.state["sessions"].insert(0, s)
        self.state["activeSessionId"] = s["id"]
        return s

    def delete_session(self, sid: str) -> None:
        self.state["sessions"] = [x for x in self.state["sessions"] if x["id"] != sid]
        if not self.state["sessions"]:
            self.add_session()
        if self.state["activeSessionId"] == sid:
            self.state["activeSessionId"] = self.state["sessions"][0]["id"]

    def touch(self, session: dict) -> None:
        session["updatedAt"] = now_ms()

    def sorted_sessions(self) -> list[dict]:
        return sorted(self.state["sessions"],
                      key=lambda s: (not s.get("pinned"), -int(s.get("updatedAt") or 0)))
