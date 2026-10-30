# -*- coding: utf-8 -*-
"""插件：把一个 .py 丢进数据目录的 plugins 文件夹，就能给模型加工具。

插件文件长这样：

    def register(reg):
        reg.add_tool(
            name="hostname",
            description="返回本机计算机名",
            func=lambda args: __import__("socket").gethostname(),
        )

注意：插件代码是直接在你机器上跑的，只放自己写的或信得过的。
"""

import importlib.util
import sys
import traceback
from pathlib import Path

import store


class Registry:
    def __init__(self):
        self.tools = []
        self.errors = []

    def add_tool(self, name, description, func, parameters=None):
        if not name or not callable(func):
            raise ValueError("add_tool 需要 name 和 func")
        self.tools.append({
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description or name,
                    "parameters": parameters or {
                        "type": "object",
                        "properties": {
                            "input": {"type": "string", "description": "参数"}
                        },
                        "required": [],
                    },
                },
            },
            "fn": func,
        })


def plugins_dir() -> Path:
    d = store.data_dir() / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(api_module) -> tuple[list[str], list[str]]:
    """加载所有插件，把工具注册进 api。返回 (成功列表, 错误列表)。"""
    ok, bad = [], []
    for path in sorted(plugins_dir().glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location("hermes_plugin_%s" % path.stem, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            registry = Registry()
            register = getattr(module, "register", None)
            if register is not None:
                register(registry)
            else:
                registry.errors.append("%s 里没有 register(reg)" % path.name)
            for tool in registry.tools:
                api_module.register_plugin_tool(tool["schema"], tool["fn"])
            ok.append(path.stem)
            bad.extend(registry.errors)
        except Exception:
            bad.append("%s: %s" % (path.name, traceback.format_exc().splitlines()[-1]))
    return ok, bad
