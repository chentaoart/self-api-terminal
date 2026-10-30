# -*- coding: utf-8 -*-
"""各种对话框：技能库、对话参数、自定义工具、模型对比、画图。"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QTextBrowser,
    QVBoxLayout,
)

import api
import md_render
import workers

DEFAULT_SKILLS = [
    {"emoji": "🌐", "name": "翻译", "prompt": "你是专业翻译。请把用户的内容翻译成中文；"
                                        "如果原文是中文，则翻译成英文。保持原文语气，只输出译文。"},
    {"emoji": "📝", "name": "总结", "prompt": "请用中文总结用户给的内容，先给三句话的摘要，"
                                        "再列要点。不要添加原文没有的信息。"},
    {"emoji": "🧩", "name": "解释代码", "prompt": "请逐步解释这段代码：整体做什么、"
                                          "关键函数与数据流、潜在问题。用中文，必要时给少量示例。"},
    {"emoji": "✍️", "name": "写作润色", "prompt": "请润色用户给出的文字：保留原意与信息量，"
                                          "让表达更自然、更准确。先给润色后的版本，再简要说明改了什么。"},
]


class SkillsDialog(QDialog):
    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("技能库")
        self.setMinimumSize(720, 460)
        self.skills = [dict(s) for s in store_.state.get("skills") or DEFAULT_SKILLS]

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        title = QLabel("技能库")
        title.setStyleSheet("font-size:14pt;font-weight:700;")
        root.addWidget(title)
        tip = QLabel("技能就是一段「系统提示词」。聊天时点一下技能标签，下一句话就会带上它。")
        tip.setStyleSheet("color:#8888a0;")
        root.addWidget(tip)

        body = QHBoxLayout()
        body.setSpacing(12)

        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setObjectName("cfgList")
        self.list.setFixedWidth(190)
        self.list.currentRowChanged.connect(self._on_select)
        left.addWidget(self.list, 1)
        row = QHBoxLayout()
        add = QPushButton("＋ 新增")
        add.setObjectName("ghostBtn")
        add.clicked.connect(self._add)
        rm = QPushButton("删除")
        rm.setObjectName("ghostBtn")
        rm.clicked.connect(self._remove)
        row.addWidget(add)
        row.addWidget(rm)
        left.addLayout(row)
        body.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(6)
        top = QHBoxLayout()
        self.f_emoji = QLineEdit()
        self.f_emoji.setFixedWidth(54)
        self.f_emoji.setMaxLength(2)
        self.f_emoji.setAlignment(Qt.AlignCenter)
        self.f_name = QLineEdit()
        top.addWidget(QLabel("图标"))
        top.addWidget(self.f_emoji)
        top.addWidget(QLabel("名称"), 0)
        top.addWidget(self.f_name, 1)
        right.addLayout(top)

        right.addWidget(QLabel("提示词"))
        self.f_prompt = QPlainTextEdit()
        self.f_prompt.setStyleSheet("background:#0b0b11;border:1px solid #24242e;"
                                    "border-radius:8px;padding:6px;")
        right.addWidget(self.f_prompt, 1)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghostBtn")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存并关闭")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(save)
        root.addLayout(foot)

        self._reload()

    # ------------------------------------------------------------------

    def _reload(self, select: int = 0):
        self.list.blockSignals(True)
        self.list.clear()
        for s in self.skills:
            self.list.addItem(QListWidgetItem("%s %s" % (s.get("emoji", ""), s.get("name", ""))))
        self.list.blockSignals(False)
        if self.skills:
            self.list.setCurrentRow(min(select, len(self.skills) - 1))
            self._on_select(self.list.currentRow())
        else:
            self._clear_form()

    def _clear_form(self):
        self.f_emoji.setText("")
        self.f_name.setText("")
        self.f_prompt.setPlainText("")

    def _on_select(self, row: int):
        if row < 0 or row >= len(self.skills):
            self._clear_form()
            return
        s = self.skills[row]
        self.f_emoji.setText(s.get("emoji", ""))
        self.f_name.setText(s.get("name", ""))
        self.f_prompt.setPlainText(s.get("prompt", ""))

    def _collect(self, row: int):
        if 0 <= row < len(self.skills):
            self.skills[row] = {
                "emoji": self.f_emoji.text().strip() or "✨",
                "name": self.f_name.text().strip() or "未命名技能",
                "prompt": self.f_prompt.toPlainText().strip(),
            }

    def _add(self):
        self._collect(self.list.currentRow())
        self.skills.append({"emoji": "✨", "name": "新技能", "prompt": ""})
        self._reload(len(self.skills) - 1)

    def _remove(self):
        row = self.list.currentRow()
        if row < 0:
            return
        if QMessageBox.question(self, "删除技能", "确定删除这个技能？") != QMessageBox.Yes:
            return
        self.skills.pop(row)
        self._reload(max(0, row - 1))

    def _save(self):
        self._collect(self.list.currentRow())
        self.store.state["skills"] = [s for s in self.skills if s.get("name")]
        self.store.save()
        self.accept()

# ---------------------------------------------------------------- 对话参数


class ParamsDialog(QDialog):
    """采样参数 + 全局系统提示词。空着就用服务端默认。"""

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("对话参数")
        self.setMinimumSize(560, 520)
        params = store_.state.get("params") or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        title = QLabel("对话参数")
        title.setStyleSheet("font-size:14pt;font-weight:700;")
        root.addWidget(title)
        tip = QLabel("留空表示用接口默认值。只影响新的请求，不改历史。")
        tip.setStyleSheet("color:#8888a0;")
        root.addWidget(tip)

        self.f_temp = QLineEdit(str(params.get("temperature") or ""))
        self.f_temp.setPlaceholderText("0 – 2，例如 0.7")
        self.f_topp = QLineEdit(str(params.get("top_p") or ""))
        self.f_topp.setPlaceholderText("0 – 1")
        self.f_maxtok = QLineEdit(str(params.get("max_tokens") or ""))
        self.f_maxtok.setPlaceholderText("例如 2048")
        for label, widget in (("温度", self.f_temp), ("top_p", self.f_topp),
                              ("最大 tokens", self.f_maxtok)):
            lab = QLabel(label)
            lab.setStyleSheet("color:#8888a0;")
            root.addWidget(lab)
            root.addWidget(widget)

        # 采样预设
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("预设"))
        for name, temp, topp in (("精确", "0.2", "0.9"), ("平衡", "0.7", "0.95"),
                                 ("发散", "1.1", "0.98")):
            btn = QPushButton(name)
            btn.setObjectName("skillChip")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _=False, t=temp, p=topp: (self.f_temp.setText(t),
                                                self.f_topp.setText(p)))
            preset_row.addWidget(btn)
        preset_row.addStretch(1)
        root.addLayout(preset_row)

        root.addWidget(QLabel("上下文上限（tokens，留空 = 自动检测）"))
        self.f_ctx = QLineEdit("" if store_.state.get("contextLimitAuto", True)
                               else str(store_.state.get("contextLimit") or ""))
        self.f_ctx.setPlaceholderText("例如 8192")
        root.addWidget(self.f_ctx)

        root.addWidget(QLabel("全局系统提示词"))
        self.f_system = QPlainTextEdit()
        self.f_system.setPlainText(store_.state.get("system") or "")
        self.f_system.setStyleSheet("background:#0b0b11;border:1px solid #24242e;"
                                    "border-radius:8px;padding:6px;")
        root.addWidget(self.f_system, 1)

        status = QLabel("")
        status.setObjectName("status")
        self.status = status
        root.addWidget(status)

        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghostBtn")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(save)
        root.addLayout(foot)

    @staticmethod
    def _number(text, low, high):
        text = (text or "").strip()
        if not text:
            return None
        value = float(text)
        if not (low <= value <= high):
            raise ValueError("数值要在 %g 到 %g 之间" % (low, high))
        return value

    def _save(self):
        try:
            temp = self._number(self.f_temp.text(), 0, 2)
            topp = self._number(self.f_topp.text(), 0, 1)
            maxtok = self._number(self.f_maxtok.text(), 1, 200000)
            ctx = self._number(self.f_ctx.text(), 256, 4000000)
        except Exception as exc:
            self.status.setText("填错了：%s" % exc)
            self.status.setStyleSheet("color:#f87171;")
            return
        self.store.state["params"] = {
            "temperature": temp,
            "top_p": topp,
            "max_tokens": int(maxtok) if maxtok is not None else None,
        }
        if ctx is None:
            self.store.state["contextLimitAuto"] = True
        else:
            self.store.state["contextLimit"] = int(ctx)
            self.store.state["contextLimitAuto"] = False
        self.store.state["system"] = self.f_system.toPlainText().strip()
        self.store.save()
        self.accept()


# ---------------------------------------------------------------- 自定义工具


class ToolsDialog(QDialog):
    """把任意 HTTP 接口包成模型能调用的工具。"""

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("自定义工具")
        self.setMinimumSize(780, 540)
        self.tools = [dict(t) for t in (store_.state.get("tools") or [])]

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)
        title = QLabel("自定义工具")
        title.setStyleSheet("font-size:14pt;font-weight:700;")
        root.addWidget(title)
        tip = QLabel("模型可以调用这些 HTTP 接口。URL / 请求体里用 {input} 代表模型传进来的内容。")
        tip.setStyleSheet("color:#8888a0;")
        root.addWidget(tip)

        body = QHBoxLayout()
        body.setSpacing(12)

        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setObjectName("cfgList")
        self.list.setFixedWidth(200)
        self.list.currentRowChanged.connect(self._on_select)
        left.addWidget(self.list, 1)
        row = QHBoxLayout()
        add = QPushButton("＋ 新增")
        add.setObjectName("ghostBtn")
        add.clicked.connect(self._add)
        rm = QPushButton("删除")
        rm.setObjectName("ghostBtn")
        rm.clicked.connect(self._remove)
        row.addWidget(add)
        row.addWidget(rm)
        left.addLayout(row)
        body.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.f_name = QLineEdit()
        self.f_name.setPlaceholderText("英文名，例如 weather")
        self.f_desc = QLineEdit()
        self.f_desc.setPlaceholderText("模型看到的说明，例如「查询某地天气」")
        self.f_hint = QLineEdit()
        self.f_hint.setPlaceholderText("input 是什么，例如「城市名」")
        self.f_method = QComboBox()
        self.f_method.addItems(["GET", "POST", "PUT"])
        self.f_url = QLineEdit()
        self.f_url.setPlaceholderText("https://api.example.com/weather?city={input}")
        self.f_headers = QPlainTextEdit()
        self.f_headers.setPlaceholderText("每行一个，例如\nX-Api-Key: abc123")
        self.f_body = QPlainTextEdit()
        self.f_body.setPlaceholderText("POST 时用，例如 {\"city\": \"{input}\"}")

        for label, widget in (("名称（英文，无空格）", self.f_name),
                              ("说明", self.f_desc),
                              ("input 的含义", self.f_hint),
                              ("方法", self.f_method),
                              ("URL", self.f_url),
                              ("请求头", self.f_headers),
                              ("请求体", self.f_body)):
            lab = QLabel(label)
            lab.setStyleSheet("color:#8888a0;")
            right.addWidget(lab)
            widget.setStyleSheet("background:#0b0b11;border:1px solid #24242e;"
                                 "border-radius:8px;padding:6px;")
            right.addWidget(widget)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghostBtn")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存并关闭")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(save)
        root.addLayout(foot)

        self._reload()

    def _reload(self, select=0):
        self.list.blockSignals(True)
        self.list.clear()
        for t in self.tools:
            self.list.addItem(QListWidgetItem(t.get("name") or "未命名"))
        self.list.blockSignals(False)
        if self.tools:
            self.list.setCurrentRow(min(select, len(self.tools) - 1))
            self._on_select(self.list.currentRow())
        else:
            self._clear()

    def _clear(self):
        for w in (self.f_name, self.f_desc, self.f_hint, self.f_url):
            w.setText("")
        self.f_headers.setPlainText("")
        self.f_body.setPlainText("")

    def _on_select(self, row):
        if row < 0 or row >= len(self.tools):
            self._clear()
            return
        t = self.tools[row]
        self.f_name.setText(t.get("name") or "")
        self.f_desc.setText(t.get("description") or "")
        self.f_hint.setText(t.get("input_hint") or "")
        self.f_method.setCurrentText((t.get("method") or "GET").upper())
        self.f_url.setText(t.get("url") or "")
        self.f_headers.setPlainText(t.get("headers") or "")
        self.f_body.setPlainText(t.get("body") or "")

    def _collect(self, row):
        if 0 <= row < len(self.tools):
            self.tools[row] = {
                "name": (self.f_name.text() or "").strip().replace(" ", "_"),
                "description": self.f_desc.text().strip(),
                "input_hint": self.f_hint.text().strip(),
                "method": self.f_method.currentText(),
                "url": self.f_url.text().strip(),
                "headers": self.f_headers.toPlainText().strip(),
                "body": self.f_body.toPlainText().strip(),
            }

    def _add(self):
        self._collect(self.list.currentRow())
        self.tools.append({"name": "", "description": "", "method": "GET", "url": ""})
        self._reload(len(self.tools) - 1)

    def _remove(self):
        row = self.list.currentRow()
        if row < 0:
            return
        if QMessageBox.question(self, "删除工具", "确定删除这个工具？") != QMessageBox.Yes:
            return
        self.tools.pop(row)
        self._reload(max(0, row - 1))

    def _save(self):
        self._collect(self.list.currentRow())
        bad = [t for t in self.tools if not t.get("name") or not t.get("url")]
        if bad:
            QMessageBox.warning(self, "自定义工具", "每个工具都要有名称和 URL")
            return
        self.store.state["tools"] = self.tools
        self.store.save()
        self.accept()


# ---------------------------------------------------------------- 模型对比


class CompareDialog(QDialog):
    """同一句话，两个模型并排回答。"""

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("模型对比")
        self.setMinimumSize(980, 680)
        self.threads = []
        self.buffers = {0: "", 1: ""}
        self.timers = {}
        self._closing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.combos = []
        for _ in range(2):
            combo = QComboBox()
            for cfg in store_.state["configs"]:
                combo.addItem("%s · %s" % (cfg.get("name") or "未命名",
                                           cfg.get("model") or "未设模型"), cfg["id"])
            combo.setStyleSheet("background:#0b0b11;border:1px solid #24242e;"
                                "border-radius:8px;padding:6px;")
            self.combos.append(combo)
            top.addWidget(combo, 1)
        root.addLayout(top)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("输入一句话，两边同时问…")
        self.input.setFixedHeight(80)
        self.input.setStyleSheet("background:#0b0b11;border:1px solid #24242e;"
                                 "border-radius:8px;padding:6px;")
        root.addWidget(self.input)

        btns = QHBoxLayout()
        self.status = QLabel("")
        self.status.setStyleSheet("color:#8888a0;")
        btns.addWidget(self.status, 1)
        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primary")
        self.send_btn.clicked.connect(self._send)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("ghostBtn")
        self.stop_btn.clicked.connect(self._stop)
        close = QPushButton("关闭")
        close.setObjectName("ghostBtn")
        close.clicked.connect(self.reject)
        btns.addWidget(self.send_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(close)
        root.addLayout(btns)

        panes = QHBoxLayout()
        panes.setSpacing(10)
        self.views = []
        for _ in range(2):
            view = QTextBrowser()
            view.setObjectName("msgText")
            view.setStyleSheet("background:#0d0d13;border:1px solid #24242e;"
                               "border-radius:10px;padding:8px;")
            panes.addWidget(view, 1)
            self.views.append(view)
        root.addLayout(panes, 1)

    def _config(self, index):
        cid = self.combos[index].currentData()
        return self.store.config(cid)

    def _send(self):
        if self.threads:
            return
        prompt = self.input.toPlainText().strip()
        if not prompt:
            return
        self.buffers = {0: "", 1: ""}
        for i in range(2):
            cfg = self._config(i)
            if cfg is None:
                continue
            self.views[i].setPlainText("")
            self.views[i].setHtml('<p style="color:#8888a0">生成中…</p>')
            thread = workers.ChatThread(
                cfg, [{"role": "user", "content": prompt}],
                self.store.state.get("params") or {}, self)
            thread.delta.connect(lambda chunk, idx=i: self._on_delta(idx, chunk))
            thread.failed.connect(lambda msg, idx=i: self._on_fail(idx, msg))
            thread.finished.connect(lambda idx=i: self._on_done(idx))
            self.threads.append(thread)
            thread.start()
        self.status.setText("生成中…")

    def _on_delta(self, index, chunk):
        if self._closing:
            return
        self.buffers[index] += chunk
        timer = self.timers.get(index)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(120)
            timer.timeout.connect(lambda idx=index: self._flush(idx))
            self.timers[index] = timer
        if not timer.isActive():
            timer.start()

    def _flush(self, index):
        if self._closing:
            return
        text = self.buffers[index]
        self.views[index].setHtml(md_render.md_to_html(text or " "))

    def _on_fail(self, index, message):
        if self._closing:
            return
        self.views[index].setHtml(
            '<p style="color:#f87171">失败：%s</p>' % message.replace("<", "&lt;"))

    def _on_done(self, index):
        if self._closing:
            return
        self._flush(index)
        alive = [t for t in self.threads if t.isRunning()]
        self.threads = alive
        if not alive:
            self.status.setText("完成")

    def _stop(self):
        for thread in self.threads:
            try:
                thread.stop()
            except Exception:
                pass
        self.status.setText("已停止")

    def closeEvent(self, event):
        self._closing = True
        for timer in self.timers.values():
            timer.stop()
        self._stop()
        for thread in self.threads:
            try:
                thread.delta.disconnect()
                thread.failed.disconnect()
                thread.finished.disconnect()
            except Exception:
                pass
            if not thread.wait(5000):
                thread.terminate()
                thread.wait(500)
        self.threads = []
        super().closeEvent(event)


# ---------------------------------------------------------------- 画图


class ImageDialog(QDialog):
    """调用 /images/generations 画一张图，存进 media 目录。"""

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("画图")
        self.setMinimumSize(560, 420)
        self.image = None
        self.worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)
        title = QLabel("画图")
        title.setStyleSheet("font-size:14pt;font-weight:700;")
        root.addWidget(title)
        tip = QLabel("调用当前配置的 /images/generations（OpenAI 兼容接口，例如 gpt-image-1 / dall-e-3）。")
        tip.setStyleSheet("color:#8888a0;")
        root.addWidget(tip)

        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("描述你想要的画面…")
        self.prompt.setStyleSheet("background:#0b0b11;border:1px solid #24242e;"
                                  "border-radius:8px;padding:6px;")
        root.addWidget(self.prompt, 1)

        row = QHBoxLayout()
        self.size = QComboBox()
        self.size.addItems(["1024x1024", "1024x768", "768x1024", "512x512"])
        row.addWidget(QLabel("尺寸"))
        row.addWidget(self.size)
        row.addStretch(1)
        self.status = QLabel("")
        self.status.setStyleSheet("color:#8888a0;")
        row.addWidget(self.status)
        root.addLayout(row)

        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghostBtn")
        cancel.clicked.connect(self.reject)
        self.gen = QPushButton("生成并插入对话")
        self.gen.setObjectName("primary")
        self.gen.clicked.connect(self._generate)
        foot.addWidget(cancel)
        foot.addWidget(self.gen)
        root.addLayout(foot)

    def _generate(self):
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            self.status.setText("先写点描述")
            return
        cfg = self.store.active_config()
        if cfg is None or not cfg.get("baseUrl"):
            self.status.setText("先在设置里配好 API")
            return
        self.gen.setEnabled(False)
        self.status.setText("生成中…")
        self.worker = workers.Worker(api.generate_image, dict(cfg), prompt,
                                     self.size.currentText())
        self.worker.ok.connect(self._done)
        self.worker.fail.connect(self._fail)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _finished(self):
        self.gen.setEnabled(True)
        if getattr(self, "_pending_close", False):
            self._pending_close = False
            self.reject()

    def closeEvent(self, event):
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            # 生成还在跑就关，会让线程对象在运行时被销毁 —— 等它跑完再关
            self._pending_close = True
            self.status.setText("还在生成，好了会自动关闭…")
            event.ignore()
            return
        super().closeEvent(event)

    def _done(self, data):
        import media
        try:
            self.image = media.add_image_bytes(bytes(data), "画图-%s.png" % self.size.currentText())
        except Exception as exc:
            self._fail(str(exc))
            return
        self.status.setText("好了")
        self.accept()

    def _fail(self, message):
        self.status.setText("失败：%s" % str(message)[:120])
