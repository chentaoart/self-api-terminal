# -*- coding: utf-8 -*-
"""自用 API 终端 —— 原生窗口版（PySide6）。

和网页版的功能对应关系：
  * 多套 API 配置 / 预设 / 拉取模型 / 测试连接  → 设置对话框
  * 话题列表：新建、搜索、置顶、改名、删除      → 左侧栏
  * 流式回答 + 推理过程 + 工具回合              → 对话区
  * 配置与话题落盘                              → %LOCALAPPDATA%\\SelfApiTerminal\\store.json
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QFontMetrics, QGuiApplication, QIcon, QKeySequence, QShortcut, QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

import api
import dialogs
import md_render
import media
import plugins
import store
import theme
import voice
import widgets

try:                      # 有 QtWebEngine 就在窗口里跑，没有就退回系统浏览器
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:         # pragma: no cover
    QWebEngineView = None

APP_TITLE = "自用 API 终端"
APP_VERSION = "2.0"


def res_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


# ---------------------------------------------------------------- 线程


from workers import ChatThread, Worker  # noqa: E402  (放在这里，替换原来的内联实现)
import workers  # noqa: E402


# ---------------------------------------------------------------- 控件


class MsgView(QTextBrowser):
    """随内容自动长高的富文本视图。"""

    def __init__(self, parent=None, hug: bool = False):
        super().__init__(parent)
        self.hug = hug
        self.setObjectName("msgText")
        self.setOpenExternalLinks(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setSizePolicy(QSizePolicy.Expanding if not hug else QSizePolicy.Fixed,
                           QSizePolicy.Fixed)
        self.document().setDocumentMargin(0)
        self.document().documentLayout().documentSizeChanged.connect(lambda *_: self.fit())
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)

    def fit(self):
        h = self.document().size().height()
        target = max(18, int(h) + 4)
        if abs(target - self.height()) > 1:
            self.setFixedHeight(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def set_markdown(self, text: str):
        try:
            html_text = md_render.md_to_html(text)
            self.setHtml(html_text)
        except Exception:
            # 渲染再出问题也不能把界面卡死
            self.setPlainText(text or "")
        if self.hug:
            fm = QFontMetrics(self.font())
            widest = 0
            for line in (text or "").split("\n"):
                widest = max(widest, fm.horizontalAdvance(line))
            width = max(56, min(int(widest * 1.05) + 28, 720))
            if abs(width - self.width()) > 2:
                self.setFixedWidth(width)
        self.fit()

    def set_plain(self, text: str):
        self.setHtml('<p style="margin:4px 0;line-height:1.6;color:#f87171;">%s</p>'
                     % _escape(text).replace("\n", "<br/>"))
        self.fit()


def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Bubble(QWidget):
    """一条消息。role: user / assistant。"""

    def __init__(self, role: str, text: str = "", parent=None,
                 attachments=None, skill=None, on_run=None, on_speak=None,
                 on_edit=None, on_delete=None, msg_index=None,
                 on_regen=None, on_continue=None):
        super().__init__(parent)
        self.role = role
        self.raw = text
        self.reason_raw = ""
        self.attachments = list(attachments or [])
        self._on_run = on_run
        self._on_speak = on_speak
        self._on_edit = on_edit
        self._on_delete = on_delete
        self._on_regen = on_regen
        self._on_continue = on_continue
        self.msg_index = msg_index
        self._view = MsgView(hug=(role == "user"))
        self._view.set_markdown(text) if text else self._view.setHtml("")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 8, 0, 8)
        row.setSpacing(11)

        self.avatar = QLabel("你" if role == "user" else "A")
        self.avatar.setObjectName("avatarU" if role == "user" else "avatarA")
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setFixedSize(30, 30)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(4)

        if role == "user":
            row.addStretch(1)
            holder = QFrame()
            holder.setObjectName("userBubble")
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(11, 6, 11, 6)
            hl.setSpacing(6)

            if skill:
                badge = QLabel("%s %s" % (skill.get("emoji", "✨"), skill.get("name", "")))
                badge.setStyleSheet("color:#c4b5fd;font-size:9pt;")
                hl.addWidget(badge)

            if self.attachments:
                hl.addWidget(self._build_attachments())

            hl.addWidget(self._view)
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.addWidget(holder)
            wrap.setMaximumWidth(780)
            row.addWidget(wrap, 0, Qt.AlignTop)
            row.addWidget(self.avatar, 0, Qt.AlignTop)
        else:
            # 推理过程（放正文上面，和模型输出的顺序一致）
            self.reason_toggle = QToolButton()
            self.reason_toggle.setObjectName("reasonToggle")
            self.reason_toggle.setCheckable(True)
            self.reason_toggle.setVisible(False)
            self.reason_toggle.setCursor(Qt.PointingHandCursor)
            self.reason_text = MsgView()
            self.reason_text.setObjectName("reasonText")
            self.reason_text.setVisible(False)
            self.reason_text.setFixedHeight(0)
            self.reason_toggle.toggled.connect(self._toggle_reason)
            content.addWidget(self.reason_toggle)
            content.addWidget(self.reason_text)

            if self.attachments:
                content.addWidget(self._build_attachments())

            content.addWidget(self._view)

            # 工具调用记录
            self.tool_label = QLabel()
            self.tool_label.setObjectName("toolLine")
            self.tool_label.setWordWrap(True)
            self.tool_label.setVisible(False)
            content.addWidget(self.tool_label)

            # 可运行的代码块
            self.run_bar = QHBoxLayout()
            self.run_bar.setContentsMargins(0, 2, 0, 0)
            self.run_bar.setSpacing(6)
            content.addLayout(self.run_bar)
            self._refresh_run_buttons()

            # 底部小按钮
            actions = QHBoxLayout()
            actions.setContentsMargins(0, 0, 0, 0)
            actions.setSpacing(2)
            self.copy_btn = QPushButton("复制")
            self.copy_btn.setObjectName("ghost")
            self.copy_btn.setCursor(Qt.PointingHandCursor)
            self.copy_btn.clicked.connect(self._copy)
            actions.addWidget(self.copy_btn)
            self.speak_btn = QPushButton("朗读")
            self.speak_btn.setObjectName("ghost")
            self.speak_btn.setCursor(Qt.PointingHandCursor)
            self.speak_btn.clicked.connect(self._speak)
            actions.addWidget(self.speak_btn)
            if on_regen is not None:
                self.regen_btn = QPushButton("重新生成")
                self.regen_btn.setObjectName("ghost")
                self.regen_btn.setCursor(Qt.PointingHandCursor)
                self.regen_btn.setVisible(msg_index is not None)
                self.regen_btn.clicked.connect(self._regen)
                actions.addWidget(self.regen_btn)
            if on_continue is not None:
                self.cont_btn = QPushButton("继续")
                self.cont_btn.setObjectName("ghost")
                self.cont_btn.setCursor(Qt.PointingHandCursor)
                self.cont_btn.setVisible(msg_index is not None)
                self.cont_btn.clicked.connect(self._cont)
                actions.addWidget(self.cont_btn)
            self.stats_label = QLabel("")
            self.stats_label.setObjectName("stats")
            actions.addWidget(self.stats_label)
            actions.addStretch(1)
            content.addLayout(actions)

            row.addWidget(self.avatar, 0, Qt.AlignTop)
            row.addLayout(content, 1)

        if self.msg_index is not None and (self._on_edit or self._on_delete):
            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self._context_menu)

    # ---------------------------------------------------------- 右键菜单

    def _context_menu(self, pos):
        # 菜单不挂父控件：一会儿重建对话会把这个气泡销毁，
        # 菜单要是它的子对象，会在自己的 exec 还没收尾时被一起删掉（直接崩）。
        menu = QMenu()
        edit = delete = None
        if self._on_edit and self.role == "user":
            edit = menu.addAction("编辑并重发")
        if self._on_delete:
            delete = menu.addAction("删除这条及之后")
        if edit is None and delete is None:
            menu.deleteLater()
            return
        index = self.msg_index
        chosen = menu.exec(self.mapToGlobal(pos))
        menu.deleteLater()
        if chosen is None:
            return
        self.apply_menu_choice("edit" if chosen == edit else "delete", index)

    def apply_menu_choice(self, choice: str, index: int):
        """菜单选完之后真正要做的事。隔开一点等菜单收尾，再重建对话。"""
        if choice == "edit" and self._on_edit is not None:
            QTimer.singleShot(60, lambda: self._on_edit(index))
        elif choice == "delete" and self._on_delete is not None:
            QTimer.singleShot(60, lambda: self._on_delete(index))

    def _build_attachments(self) -> QWidget:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        images = [a for a in self.attachments if a.get("kind") == "image"]
        files = [a for a in self.attachments if a.get("kind") != "image"]

        row = QHBoxLayout()
        row.setSpacing(6)
        for att in images:
            row.addWidget(widgets.ImageThumb(att))
        row.addStretch(1)
        if images:
            lay.addLayout(row)

        for att in files:
            line = QHBoxLayout()
            line.addWidget(widgets.FileChip(att))
            line.addStretch(1)
            lay.addLayout(line)
        return holder

    # ---------------------------------------------------------- 运行

    def _code_blocks(self):
        import re
        pattern = re.compile(r"```([A-Za-z0-9_+-]*)\n([\s\S]*?)```")
        out = []
        for lang, code in pattern.findall(self.raw or ""):
            lang = (lang or "").lower()
            if lang in ("html", "htm", "svg") or (not lang and "<html" in code.lower()):
                out.append((lang or "html", code))
        return out

    def _all_blocks(self):
        import re
        pattern = re.compile(r"```([A-Za-z0-9_+-]*)\n([\s\S]*?)```")
        return pattern.findall(self.raw or "")

    def _refresh_run_buttons(self):
        if self.role != "assistant" or not hasattr(self, "run_bar"):
            return
        while self.run_bar.count():
            item = self.run_bar.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        blocks = self._code_blocks()
        if self._all_blocks():
            copy_btn = QPushButton("复制代码")
            copy_btn.setObjectName("ghost")
            copy_btn.setCursor(Qt.PointingHandCursor)
            copy_btn.clicked.connect(self._copy_code)
            self.run_bar.addWidget(copy_btn)
        for idx, (lang, code) in enumerate(blocks[:3]):
            btn = QPushButton("▶ 运行 %s" % ("HTML" if lang in ("html", "htm") else lang.upper()))
            btn.setObjectName("ghost")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, c=code, l=lang: self._run_code(c, l))
            self.run_bar.addWidget(btn)
        self.run_bar.addStretch(1)

    def _copy_code(self):
        blocks = self._all_blocks()
        if not blocks:
            return
        text = "\n\n".join(code for _lang, code in blocks)
        QApplication.clipboard().setText(text)

    def _run_code(self, code: str, lang: str):
        if self._on_run is not None:
            self._on_run(code, lang)

    def _speak(self):
        if self._on_speak is not None:
            self._on_speak(self.raw)

    def _regen(self):
        if self._on_regen is None or self.msg_index is None:
            return
        index = self.msg_index
        QTimer.singleShot(0, lambda: self._on_regen(index))

    def _cont(self):
        if self._on_continue is None or self.msg_index is None:
            return
        index = self.msg_index
        QTimer.singleShot(0, lambda: self._on_continue(index))

    def set_stats(self, text: str):
        if hasattr(self, "stats_label"):
            self.stats_label.setText(text)

    def finish(self, index: int):
        """流式结束后补上序号，把「重新生成 / 继续」露出来。"""
        self.msg_index = index
        for name in ("regen_btn", "cont_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                btn.setVisible(True)

    # ---------------------------------------------------------- 推理

    def _toggle_reason(self, on: bool):
        self.reason_text.setVisible(on and bool(self.reason_raw))
        if self.reason_text.isVisible():
            self.reason_text.set_markdown(self.reason_raw)
            self.reason_text.fit()
        else:
            self.reason_text.setFixedHeight(0)
        self._refresh_reason_label()

    def _refresh_reason_label(self):
        if not hasattr(self, "reason_toggle"):
            return
        n = len(self.reason_raw)
        arrow = "▾" if self.reason_toggle.isChecked() else "▸"
        self.reason_toggle.setText("%s 思考过程（%d 字）" % (arrow, n))

    def set_reasoning(self, text: str):
        self.reason_raw = text
        self.reason_toggle.setVisible(bool(text))
        self._refresh_reason_label()
        if self.reason_toggle.isChecked():
            self.reason_text.set_markdown(text)
            self.reason_text.fit()
        # 第一段推理出现时自动展开
        if text and not getattr(self, "_auto_opened", False):
            self._auto_opened = True
            self.reason_toggle.setChecked(True)

    # ---------------------------------------------------------- 文本

    def set_text(self, text: str):
        self.raw = text
        self._view.set_markdown(text)
        if self.role == "assistant":
            self._refresh_run_buttons()

    def append_text(self, chunk: str):
        self.raw += chunk
        self._view.set_markdown(self.raw)

    def set_tool(self, name: str, args: str):
        text = "🔧 %s(%s)" % (name, _short(args, 120))
        old = self.tool_label.text()
        self.tool_label.setText((old + "\n" + text) if old else text)
        self.tool_label.setVisible(True)

    def add_tool_result(self, name: str, result: str):
        line = "   ↳ %s" % _short(result.replace("\n", " "), 160)
        self.tool_label.setText(self.tool_label.text() + "\n" + line)
        self.tool_label.setVisible(True)

    def view_error(self, message: str):
        body = _escape(message).replace("\n", "<br/>")
        self._view.setHtml(
            '<p style="margin:4px 0;line-height:1.6;color:#f87171;">'
            '<b>⚠️ 请求失败</b><br/><span style="color:#e6a3a3;font-size:9.5pt;">%s</span></p>' % body)
        self._view.fit()

    def _copy(self):
        QApplication.clipboard().setText(self.raw)

    def empty(self) -> bool:
        return not self.raw.strip()


def _short(text: str, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _alive(widget) -> bool:
    """Qt 控件是否还活着（用已销毁的对象会直接让进程消失）。"""
    if widget is None:
        return False
    try:
        from shiboken6 import isValid
        return bool(isValid(widget))
    except Exception:
        return True


class ToolLine(QWidget):
    """历史里的工具结果，压成一行灰字。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(41, 0, 0, 0)
        label = QLabel(text)
        label.setObjectName("toolLine")
        label.setWordWrap(True)
        lay.addWidget(label)


class ChatArea(QScrollArea):
    followChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chat")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("chatBody")
        self.vbox = QVBoxLayout(self.body)
        self.vbox.setContentsMargins(22, 12, 22, 12)
        self.vbox.setSpacing(2)
        self.vbox.addStretch(1)
        self.setWidget(self.body)
        self._empty = None
        self._follow = True
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _on_scroll(self, _value):
        following = self.near_bottom()
        if following != self._follow:
            self._follow = following
            self.followChanged.emit(following)

    def is_following(self) -> bool:
        return self._follow

    def add(self, widget: QWidget):
        self.vbox.insertWidget(self.vbox.count() - 1, widget)
        if self._follow:
            QTimer.singleShot(0, self.to_bottom)

    def clear(self):
        self._empty = None
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def remove_empty(self):
        if self._empty is not None:
            self._empty.hide()
            self._empty.deleteLater()
            self._empty = None

    def to_bottom(self, force: bool = False):
        if not force and not self._follow:
            return
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._follow = True

    def show_empty(self):
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 110, 0, 0)
        lay.setSpacing(12)
        logo = QLabel("A")
        logo.setObjectName("brandMark")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(54, 54)
        title = QLabel("开始对话")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:16pt;font-weight:700;color:#e9e9f0;")
        sub = QLabel("在左下角「API 设置」里填好地址和密钥，再回到这里提问")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color:#8888a0;")
        lay.addWidget(logo, 0, Qt.AlignHCenter)
        lay.addWidget(title)
        lay.addWidget(sub)
        self._empty = holder
        self.add(holder)

    def near_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.maximum() - bar.value() < 80


class Composer(QPlainTextEdit):
    submitted = Signal()
    image_pasted = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("input")
        self.setPlaceholderText("发消息…（Enter 发送 / Shift+Enter 换行，输入 / 看指令，可拖入文件或粘贴图片）")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.document().setDocumentMargin(8)
        self.setFixedHeight(52)
        self.textChanged.connect(self._autosize)
        self.document().documentLayout().documentSizeChanged.connect(lambda *_: self._autosize())
        self.setAcceptDrops(True)

    def _autosize(self):
        h = int(self.document().size().height()) + 16
        self.setFixedHeight(max(52, min(h, 190)))

    def insertFromMimeData(self, source):  # noqa: N802 (Qt 命名)
        if source.hasImage():
            image = source.imageData()
            if image is not None:
                self.image_pasted.emit(image)
                return
        super().insertFromMimeData(source)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------- 设置对话框


class SettingsDialog(QDialog):
    def __init__(self, store_: store.Store, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("API 设置")
        self.setMinimumSize(760, 520)
        self.current_id = store_.state["activeId"]

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("API 设置")
        title.setStyleSheet("font-size:14pt;font-weight:700;")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(14)

        # 左：配置列表
        left = QVBoxLayout()
        left.setSpacing(6)
        self.list = QListWidget()
        self.list.setObjectName("cfgList")
        self.list.setFixedWidth(220)
        self.list.currentItemChanged.connect(self._on_select)
        left.addWidget(self.list, 1)
        btns = QHBoxLayout()
        add = QPushButton("＋ 新增")
        add.setObjectName("ghostBtn")
        add.clicked.connect(self._add)
        rm = QPushButton("删除")
        rm.setObjectName("ghostBtn")
        rm.clicked.connect(self._remove)
        btns.addWidget(add)
        btns.addWidget(rm)
        left.addLayout(btns)
        body.addLayout(left)

        # 右：表单
        right = QVBoxLayout()
        right.setSpacing(8)

        def field(label):
            lab = QLabel(label)
            lab.setObjectName("fieldLabel")
            right.addWidget(lab)

        field("名称")
        self.f_name = QLineEdit()
        right.addWidget(self.f_name)

        field("服务预设")
        self.f_preset = QComboBox()
        for pid, pname, _url in store.PRESETS:
            self.f_preset.addItem(pname, pid)
        self.f_preset.currentIndexChanged.connect(self._apply_preset)
        right.addWidget(self.f_preset)

        field("Base URL")
        self.f_base = QLineEdit()
        self.f_base.setPlaceholderText("https://api.deepseek.com/v1")
        right.addWidget(self.f_base)

        field("API Key")
        self.f_key = QLineEdit()
        self.f_key.setEchoMode(QLineEdit.Password)
        self.f_key.setPlaceholderText("sk-…（本机服务随便填）")
        right.addWidget(self.f_key)

        field("模型")
        mrow = QHBoxLayout()
        self.f_model = QComboBox()
        self.f_model.setEditable(True)
        mrow.addWidget(self.f_model, 1)
        self.fetch_btn = QPushButton("拉取模型")
        self.fetch_btn.setObjectName("ghostBtn")
        self.fetch_btn.clicked.connect(self._fetch_models)
        mrow.addWidget(self.fetch_btn)
        right.addLayout(mrow)

        row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("ghostBtn")
        self.test_btn.clicked.connect(self._test)
        row.addWidget(self.test_btn)
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        right.addLayout(row)
        right.addStretch(1)
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

        self._reload_list()

    # ---------------------------------------------------------- 列表

    def _reload_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        for cfg in self.store.state["configs"]:
            item = QListWidgetItem(cfg.get("name") or "未命名")
            item.setData(Qt.UserRole, cfg["id"])
            item.setToolTip(cfg.get("model") or "")
            self.list.addItem(item)
            if cfg["id"] == self.current_id:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._on_select(self.list.currentItem(), None)

    def _selected(self) -> dict | None:
        item = self.list.currentItem()
        return self.store.config(item.data(Qt.UserRole)) if item else None

    def _on_select(self, item, _prev):
        cfg = self._selected()
        if not cfg:
            return
        self.current_id = cfg["id"]
        self.f_name.setText(cfg.get("name", ""))
        self.f_base.setText(cfg.get("baseUrl", ""))
        self.f_key.setText(cfg.get("apiKey", ""))
        self.f_model.clear()
        if cfg.get("model"):
            self.f_model.addItem(cfg["model"])
            self.f_model.setCurrentText(cfg["model"])
        pid = cfg.get("providerId", "custom")
        idx = self.f_preset.findData(pid)
        self.f_preset.blockSignals(True)
        self.f_preset.setCurrentIndex(idx if idx >= 0 else self.f_preset.count() - 1)
        self.f_preset.blockSignals(False)
        self._set_status("", "")

    def _apply_preset(self, _idx):
        pid = self.f_preset.currentData()
        for p_id, p_name, p_url in store.PRESETS:
            if p_id == pid:
                if p_url:
                    self.f_base.setText(p_url)
                if not self.f_name.text().strip():
                    self.f_name.setText(p_name)
                break

    def _collect(self) -> dict:
        cfg = self._selected()
        if not cfg:
            raise ValueError("没有选中的配置")
        cfg["name"] = self.f_name.text().strip() or "未命名"
        cfg["baseUrl"] = self.f_base.text().strip().rstrip("/")
        cfg["apiKey"] = self.f_key.text().strip()
        cfg["model"] = self.f_model.currentText().strip()
        cfg["providerId"] = self.f_preset.currentData() or "custom"
        return cfg

    def _add(self):
        cfg = store.default_config(len(self.store.state["configs"]) + 1)
        self.store.state["configs"].append(cfg)
        self.current_id = cfg["id"]
        self._reload_list()

    def _remove(self):
        if len(self.store.state["configs"]) <= 1:
            self._set_status("至少保留一个配置", "err")
            return
        cfg = self._selected()
        if not cfg:
            return
        if QMessageBox.question(self, "删除配置", "确定删除「%s」？" % (cfg.get("name") or "未命名")) \
                != QMessageBox.Yes:
            return
        self.store.state["configs"] = [c for c in self.store.state["configs"] if c["id"] != cfg["id"]]
        if self.store.state["activeId"] == cfg["id"]:
            self.store.state["activeId"] = self.store.state["configs"][0]["id"]
        self.current_id = self.store.state["activeId"]
        self._reload_list()

    # ---------------------------------------------------------- 动作

    def _set_status(self, text: str, kind: str = ""):
        if self._closed():
            return
        color = {"ok": theme.OK, "err": theme.ERR, "run": theme.WARN}.get(kind, theme.MUTED)
        self.status.setStyleSheet("color:%s;" % color)
        self.status.setText(text)

    def _fetch_models(self):
        try:
            cfg = self._collect()
        except Exception as exc:
            self._set_status(str(exc), "err")
            return
        if not cfg["baseUrl"]:
            self._set_status("先填 Base URL", "err")
            return
        self.fetch_btn.setEnabled(False)
        self._set_status("正在拉取模型列表…（最多 20 秒）", "run")
        workers.run_bg(api.list_models, cfg,
                       on_ok=self._on_models, on_fail=self._on_models_fail)

    def _on_models_fail(self, err):
        if self._closed():
            return
        self.fetch_btn.setEnabled(True)
        self._set_status("拉取失败：%s" % _short(err, 160), "err")

    def _on_models(self, models):
        if self._closed():
            return
        self.fetch_btn.setEnabled(True)
        if not models:
            self._set_status("接口成功，但没解析到模型", "err")
            return
        current = self.f_model.currentText().strip()
        self.f_model.clear()
        self.f_model.addItems(models)
        if current in models:
            self.f_model.setCurrentText(current)
        elif models:
            self.f_model.setCurrentIndex(0)
        self._set_status("共 %d 个模型" % len(models), "ok")

    def _test(self):
        try:
            cfg = self._collect()
        except Exception as exc:
            self._set_status(str(exc), "err")
            return
        self.test_btn.setEnabled(False)
        self._set_status("请求中…（最多 25 秒）", "run")
        workers.run_bg(api.test_connection, cfg,
                       on_ok=self._on_test, on_fail=self._on_test_fail)

    def _on_test(self, result):
        if self._closed():
            return
        self.test_btn.setEnabled(True)
        ok, msg = result
        self._set_status(msg, "ok" if ok else "err")

    def _on_test_fail(self, err):
        if self._closed():
            return
        self.test_btn.setEnabled(True)
        self._set_status("失败：%s" % _short(err, 160), "err")

    def _save(self):
        try:
            cfg = self._collect()
        except Exception as exc:
            self._set_status(str(exc), "err")
            return
        self.store.state["activeId"] = cfg["id"]
        self.store.save()
        self.accept()

    def done(self, result):
        """关窗只标记一下；后台请求由 workers 自己收尾，不在这里销毁线程。"""
        self._closing = True
        super().done(result)

    def _closed(self) -> bool:
        return getattr(self, "_closing", False)


# ---------------------------------------------------------------- 主窗口


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = store.Store()
        self.thread: ChatThread | None = None
        self.bubble: Bubble | None = None
        self.attachments: list[dict] = []
        self.active_skill: dict | None = None
        self.tts = None
        self.preview_window = None
        self._stream_session = None
        self._append_index = None
        self._closing = False
        self.auto_speak = bool(self.store.state.get("ttsAuto"))
        self.show_reasoning = True
        self._acc = ""
        self._reason = ""
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(90)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._flush_render)

        self.setWindowTitle(APP_TITLE)
        icon = res_path("icon.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setMinimumSize(900, 620)
        self._build_ui()
        self._apply_state()
        QTimer.singleShot(350, self._first_run_hint)

    # ------------------------------------------------------------- UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 侧边栏
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(264)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(12, 14, 12, 12)
        side.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        mark = QLabel("A")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(26, 26)
        brand = QLabel(APP_TITLE)
        brand.setObjectName("brand")
        head.addWidget(mark)
        head.addWidget(brand, 1)
        side.addLayout(head)

        self.new_btn = QPushButton("＋  新话题")
        self.new_btn.setObjectName("newChat")
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.clicked.connect(self.new_session)
        side.addWidget(self.new_btn)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("搜索话题…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_sessions)
        side.addWidget(self.search)

        self.session_list = QListWidget()
        self.session_list.setObjectName("sessions")
        self.session_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.session_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._session_menu)
        self.session_list.itemClicked.connect(self._pick_session)
        self.session_list.itemDoubleClicked.connect(lambda _i: self._rename_session())
        side.addWidget(self.session_list, 1)

        foot = QHBoxLayout()
        foot.setSpacing(6)
        self.settings_btn = QPushButton("⚙  API 设置")
        self.settings_btn.setObjectName("ghostBtn")
        self.settings_btn.clicked.connect(self.open_settings)
        foot.addWidget(self.settings_btn, 1)
        side.addLayout(foot)
        outer.addWidget(self.sidebar)

        # 主区
        main = QWidget()
        main_lay = QVBoxLayout(main)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(56)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 8, 14, 8)
        hl.setSpacing(8)

        self.menu_btn = QPushButton("☰")
        self.menu_btn.setObjectName("iconBtn")
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.clicked.connect(self.toggle_sidebar)
        hl.addWidget(self.menu_btn)

        self.title_label = QLabel("新话题")
        self.title_label.setObjectName("pageTitle")
        hl.addWidget(self.title_label, 1)

        self.cfg_chip = QPushButton("未配置 ▾")
        self.cfg_chip.setObjectName("cfgChip")
        self.cfg_chip.setCursor(Qt.PointingHandCursor)
        self.cfg_chip.clicked.connect(self._show_cfg_menu)
        hl.addWidget(self.cfg_chip)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("cfgChip")
        self.clear_btn.setToolTip("清空当前话题")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_session)
        hl.addWidget(self.clear_btn)

        self.tts_btn = QPushButton("🔊")
        self.tts_btn.setObjectName("iconBtn")
        self.tts_btn.setCheckable(True)
        self.tts_btn.setToolTip("自动朗读回答")
        self.tts_btn.setCursor(Qt.PointingHandCursor)
        self.tts_btn.toggled.connect(self._toggle_auto_speak)
        hl.addWidget(self.tts_btn)

        self.reason_btn = QPushButton("思")
        self.reason_btn.setObjectName("iconBtn")
        self.reason_btn.setCheckable(True)
        self.reason_btn.setChecked(True)
        self.reason_btn.setToolTip("显示/隐藏思考过程")
        self.reason_btn.setCursor(Qt.PointingHandCursor)
        self.reason_btn.toggled.connect(self._toggle_reasoning)
        hl.addWidget(self.reason_btn)

        self.bottom_btn = QPushButton("⤓")
        self.bottom_btn.setObjectName("iconBtn")
        self.bottom_btn.setToolTip("回到底部")
        self.bottom_btn.setCursor(Qt.PointingHandCursor)
        self.bottom_btn.clicked.connect(lambda: self.chat.to_bottom(force=True))
        hl.addWidget(self.bottom_btn)

        self.ctx_label = QPushButton("")
        self.ctx_label.setObjectName("ctxChip")
        self.ctx_label.setCursor(Qt.PointingHandCursor)
        self.ctx_label.setToolTip("当前话题的大致上下文占用（按字数估算），点一下有用法")
        self.ctx_label.clicked.connect(self._ctx_menu)
        hl.addWidget(self.ctx_label)

        self.more_btn = QPushButton("⋯")
        self.more_btn.setObjectName("iconBtn")
        self.more_btn.setToolTip("更多")
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.clicked.connect(self._show_more_menu)
        hl.addWidget(self.more_btn)

        self.settings_icon = QPushButton("⚙")
        self.settings_icon.setObjectName("iconBtn")
        self.settings_icon.setToolTip("API 设置")
        self.settings_icon.setCursor(Qt.PointingHandCursor)
        self.settings_icon.clicked.connect(self.open_settings)
        hl.addWidget(self.settings_icon)
        main_lay.addWidget(header)

        self.chat = ChatArea()
        self.chat.followChanged.connect(self._on_follow_changed)
        main_lay.addWidget(self.chat, 1)

        # 输入区
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(22, 6, 22, 12)
        bl.setSpacing(6)

        self.skill_bar = QWidget()
        self.skill_layout = QHBoxLayout(self.skill_bar)
        self.skill_layout.setContentsMargins(0, 0, 0, 0)
        self.skill_layout.setSpacing(6)
        bl.addWidget(self.skill_bar)

        self.attach_bar = widgets.AttachmentBar()
        self.attach_bar.removed.connect(self._remove_attachment)
        bl.addWidget(self.attach_bar)

        self.composer_frame = QFrame()
        self.composer_frame.setObjectName("composer")
        cl = QHBoxLayout(self.composer_frame)
        cl.setContentsMargins(8, 4, 8, 4)
        cl.setSpacing(6)

        self.attach_btn = QPushButton("📎")
        self.attach_btn.setObjectName("iconBtn")
        self.attach_btn.setToolTip("添加图片或文件（也可以拖进来、Ctrl+V 粘贴图片）")
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.clicked.connect(self.pick_files)
        cl.addWidget(self.attach_btn, 0, Qt.AlignBottom)

        self.voice_btn = QPushButton("🎤")
        self.voice_btn.setObjectName("iconBtn")
        self.voice_btn.setToolTip("语音输入（需要麦克风）")
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        self.voice_btn.clicked.connect(self.start_voice)
        cl.addWidget(self.voice_btn, 0, Qt.AlignBottom)

        self.composer = Composer()
        self.composer.submitted.connect(self.send)
        self.composer.image_pasted.connect(self._attach_image)
        cl.addWidget(self.composer, 1)
        self.send_btn = QPushButton("↑")
        self.send_btn.setObjectName("send")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setToolTip("发送（Enter）")
        self.send_btn.clicked.connect(self.send)
        cl.addWidget(self.send_btn, 0, Qt.AlignBottom)
        self.stop_btn = QPushButton("■")
        self.stop_btn.setObjectName("sendStop")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setToolTip("停止生成")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setVisible(False)
        cl.addWidget(self.stop_btn, 0, Qt.AlignBottom)
        bl.addWidget(self.composer_frame)
        hint = QLabel("配置存在本机 · 请求由本程序直接发出，不经浏览器")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignCenter)
        bl.addWidget(hint)
        main_lay.addWidget(bottom)
        outer.addWidget(main, 1)

        QShortcut(QKeySequence("Ctrl+K"), self, self.new_session)
        QShortcut(QKeySequence("Ctrl+B"), self, self.toggle_sidebar)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, self.stop)
        QShortcut(QKeySequence("Ctrl+O"), self, self.pick_files)
        self.setAcceptDrops(True)

    # ----------------------------------------------------------- 状态

    def _apply_state(self):
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        want_w, want_h = 1200, 820
        if avail is not None:
            want_w = min(want_w, int(avail.width() * 0.92))
            want_h = min(want_h, int(avail.height() * 0.92))
        self.setMinimumSize(min(900, want_w), min(620, want_h))

        placed = False
        geo = self.store.state.get("geometry")
        if isinstance(geo, list) and len(geo) == 4 and avail is not None:
            try:
                x, y, w, h = (int(v) for v in geo)
            except Exception:
                x = y = w = h = 0
            inside = (avail.x() - 40 <= x <= avail.x() + avail.width() - 200 and
                      avail.y() - 10 <= y <= avail.y() + avail.height() - 150 and
                      w <= avail.width() and h <= avail.height())
            if inside:
                self.setGeometry(x, y, w, h)
                placed = True
        if not placed:
            self.resize(want_w, want_h)
            if avail is not None:
                self.move(avail.x() + max(0, (avail.width() - want_w) // 2),
                          avail.y() + max(0, (avail.height() - want_h) // 2))
        self.refresh_sessions()
        self.render_session()
        self.refresh_chip()
        self.update_title()
        self._refresh_skills()
        self._apply_custom_tools()
        self.plugin_status = plugins.load(api)
        self._detect_ctx()
        self.tts_btn.blockSignals(True)
        self.tts_btn.setChecked(bool(self.store.state.get("ttsAuto")))
        self.tts_btn.blockSignals(False)

    def _first_run_hint(self):
        cfg = self.store.active_config()
        if cfg is None or not (cfg.get("baseUrl") and cfg.get("model")):
            self.open_settings()

    # ----------------------------------------------------------- 附件

    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片或文件", "",
            "常用 (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.txt *.md *.py *.js *.json "
            "*.html *.css *.csv *.log *.yaml *.yml);;图片 (*.png *.jpg *.jpeg *.webp *.gif *.bmp);;"
            "所有文件 (*.*)")
        if paths:
            self.add_paths(paths)

    def add_paths(self, paths):
        errors = []
        for p in paths:
            try:
                self.attachments.append(media.add_path(p))
            except Exception as exc:
                errors.append(str(exc))
        self._refresh_attachments()
        if errors:
            QMessageBox.warning(self, "附件", "\n".join(errors[:5]))

    def _attach_image(self, image):
        import tempfile

        tmp = Path(tempfile.gettempdir()) / ("hermes-paste-%d.png" % os.getpid())
        try:
            if not image.save(str(tmp), "PNG"):
                raise media.AttachError("这张图保存不了")
            self.attachments.append(media.add_path(tmp))
        except Exception as exc:
            QMessageBox.warning(self, "图片", str(exc))
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
        self._refresh_attachments()

    def _remove_attachment(self, att):
        self.attachments = [a for a in self.attachments if a is not att]
        self._refresh_attachments()

    def _refresh_attachments(self):
        self.attach_bar.set_items(self.attachments)

    # ----------------------------------------------------------- 语音

    def start_voice(self):
        if getattr(self, "_voice_worker", None) is not None:
            return
        self.voice_btn.setEnabled(False)
        self.voice_btn.setText("…")
        worker = Worker(voice.listen, 8)
        worker.ok.connect(self._voice_done)
        worker.fail.connect(self._voice_fail)
        worker.finished.connect(self._voice_cleanup)
        self._voice_worker = worker
        worker.start()

    def _voice_cleanup(self):
        self._voice_worker = None
        self.voice_btn.setEnabled(True)
        self.voice_btn.setText("🎤")

    def _voice_done(self, text):
        current = self.composer.toPlainText().strip()
        self.composer.setPlainText((current + " " + text).strip() if current else text)
        self.composer.setFocus()

    def _voice_fail(self, message):
        QMessageBox.information(self, "语音输入", str(message))

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasUrls() or md.hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasImage():
            image = md.imageData()
            if image is not None:
                self._attach_image(image)
        paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        if paths:
            self.add_paths(paths)
        event.acceptProposedAction()

    # ----------------------------------------------------------- 技能

    def _refresh_skills(self):
        while self.skill_layout.count():
            item = self.skill_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for skill in self.store.state.get("skills") or []:
            btn = QPushButton("%s %s" % (skill.get("emoji", "✨"), skill.get("name", "")))
            btn.setObjectName("skillChip")
            btn.setCheckable(True)
            btn.setChecked(bool(self.active_skill) and
                           self.active_skill.get("name") == skill.get("name"))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip((skill.get("prompt") or "")[:300])
            btn.clicked.connect(lambda _=False, s=skill: self._toggle_skill(s))
            self.skill_layout.addWidget(btn)
        add = QPushButton("＋ 技能")
        add.setObjectName("skillChip")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.open_skills)
        self.skill_layout.addWidget(add)
        self.skill_layout.addStretch(1)

    def _toggle_skill(self, skill):
        if self.active_skill and self.active_skill.get("name") == skill.get("name"):
            self.active_skill = None
        else:
            self.active_skill = dict(skill)
        self._refresh_skills()

    def open_skills(self):
        dlg = dialogs.SkillsDialog(self.store, self)
        if dlg.exec() == QDialog.Accepted:
            self.active_skill = None
            self._refresh_skills()

    # ----------------------------------------------------------- 菜单

    def _show_more_menu(self):
        menu = QMenu(self)
        menu.addAction("技能库…", self.open_skills)
        menu.addAction("本话题系统提示词…", self.open_session_system)
        menu.addAction("对话参数…", self.open_params)
        menu.addAction("自定义工具…", self.open_tools)
        menu.addAction("打开插件文件夹…", self.open_plugins_dir)
        menu.addAction("打开数据目录（含 crash.log）…", self.open_data_dir)
        menu.addSeparator()
        menu.addAction("模型对比…", self.open_compare)
        menu.addAction("画图…", self.open_image)
        menu.addSeparator()
        menu.addAction("导出备份…", self.export_backup)
        menu.addAction("导入备份…", self.import_backup)
        menu.addSeparator()
        act_preview = menu.addAction("网页预览用系统浏览器")
        act_preview.setCheckable(True)
        act_preview.setChecked(bool(self.store.state.get("previewExternal")))
        chosen = menu.exec(self.more_btn.mapToGlobal(QPoint(0, self.more_btn.height() + 4)))
        if chosen == act_preview:
            self.store.state["previewExternal"] = act_preview.isChecked()
            self.store.save()

    def open_plugins_dir(self):
        folder = plugins.plugins_dir()
        ok, bad = getattr(self, "plugin_status", ([], []))
        text = "已加载插件：%s\n" % ("、".join(ok) if ok else "（无）")
        if bad:
            text += "\n有问题：\n" + "\n".join(bad[:5])
        QMessageBox.information(self, "插件", text + "\n\n文件夹：\n%s" % folder)
        try:
            os.startfile(str(folder))
        except Exception:
            pass

    def open_data_dir(self):
        folder = store.data_dir()
        log_path = folder / "crash.log"
        text = "数据目录：\n%s\n\n" % folder
        if log_path.exists():
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
                text += "crash.log 最后一段：\n%s" % tail
            except Exception:
                text += "crash.log 读不出来"
        else:
            text += "还没有崩溃记录（crash.log 不存在）。"
        QMessageBox.information(self, "数据目录", text)
        try:
            os.startfile(str(folder))
        except Exception:
            pass

    # ----------------------------------------------------------- 新对话框

    def _apply_custom_tools(self):
        api.set_custom_tools(self.store.state.get("tools") or [])

    def open_params(self):
        dlg = dialogs.ParamsDialog(self.store, self)
        dlg.exec()

    def open_tools(self):
        dlg = dialogs.ToolsDialog(self.store, self)
        if dlg.exec() == QDialog.Accepted:
            self._apply_custom_tools()

    def open_compare(self):
        dlg = dialogs.CompareDialog(self.store, self)
        dlg.exec()

    def open_image(self):
        dlg = dialogs.ImageDialog(self.store, self)
        if dlg.exec() != QDialog.Accepted or not dlg.image:
            return
        session = self.store.active_session()
        session["messages"].append({
            "role": "assistant",
            "content": "（画好的图）",
            "attachments": [dlg.image],
        })
        self.store.touch(session)
        self.store.save()
        self.refresh_sessions()
        self.render_session()

    def export_backup(self):
        import time

        default = str(Path.home() / ("hermes-backup-%s.json" % time.strftime("%Y%m%d")))
        path, _ = QFileDialog.getSaveFileName(self, "导出备份", default, "JSON (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(self.store.state, ensure_ascii=False, indent=1), encoding="utf-8")
            QMessageBox.information(self, "备份", "已导出到：\n%s" % path)
        except Exception as exc:
            QMessageBox.warning(self, "备份", "导出失败：%s" % exc)

    def import_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入备份", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "sessions" not in data:
                raise ValueError("这不是本程序的备份文件")
        except Exception as exc:
            QMessageBox.warning(self, "备份", "读取失败：%s" % exc)
            return
        if QMessageBox.question(self, "导入备份",
                                "导入会覆盖当前的配置和话题，继续？") != QMessageBox.Yes:
            return
        self.store.state = store.Store._normalize(data)
        self.store.save()
        self._apply_state()
        self._refresh_skills()
        QMessageBox.information(self, "备份", "导入完成")

    # ----------------------------------------------------------- 朗读

    def _ensure_tts(self) -> bool:
        if self.tts is None:
            import tts as tts_mod  # 朗读用到时才加载语音库

            self.tts = tts_mod.Tts()
        if not self.tts.ready:
            QMessageBox.information(self, "朗读", self.tts.error or "系统里没有可用的语音")
            return False
        return True

    def speak(self, text: str):
        if not (text or "").strip():
            return
        if self._ensure_tts():
            self.tts.speak(text)

    def stop_speaking(self):
        if self.tts is not None:
            self.tts.stop()

    def _toggle_auto_speak(self, on: bool):
        self.auto_speak = on
        self.store.state["ttsAuto"] = on
        self.store.save()
        if on and not self._ensure_tts():
            self.tts_btn.blockSignals(True)
            self.tts_btn.setChecked(False)
            self.tts_btn.blockSignals(False)
            self.auto_speak = False

    def _toggle_reasoning(self, on: bool):
        self.show_reasoning = on
        if self.thread is None:
            self.render_session()

    # ----------------------------------------------------------- 侧边栏

    def toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def _on_follow_changed(self, following: bool):
        self.bottom_btn.setText("⤓" if following else "⤓●")
        self.bottom_btn.setToolTip("回到底部" if following else "有新内容，点这里回到底部")

    # ----------------------------------------------------------- 上下文上限

    def _detect_ctx(self):
        """llama.cpp 的 /props 里有 n_ctx，能读到就用它，省得用户手填。"""
        if not self.store.state.get("contextLimitAuto", True):
            return
        if getattr(self, "_ctx_worker", None) is not None:
            return
        cfg = self.store.active_config()
        if not cfg or not cfg.get("baseUrl"):
            return
        self._ctx_worker = workers.run_bg(api.fetch_context_limit, dict(cfg),
                                          on_ok=self._on_ctx_detected)
        self._ctx_worker.finished.connect(lambda: setattr(self, "_ctx_worker", None))

    def _on_ctx_detected(self, result):
        if self._closing or not _alive(self.ctx_label):
            return
        try:
            limit, source = result
        except Exception:
            return
        if limit and self.store.state.get("contextLimitAuto", True):
            self.store.state["contextLimit"] = int(limit)
            self.store.save()
            self.ctx_label.setToolTip("上下文上限 %d（自动检测：%s）" % (limit, source))
            self._update_ctx()

    # ----------------------------------------------------------- 上下文占用

    def _estimate_tokens(self, messages=None) -> int:
        session = self.store.active_session()
        msgs = messages if messages is not None else (session.get("messages") or [])
        chars = 0
        for msg in msgs:
            content = msg.get("content")
            if isinstance(content, str):
                chars += len(content)
            for att in msg.get("attachments") or []:
                chars += len(str(att.get("text") or ""))
        return int(chars / 1.6)      # 中英混排的粗估

    def _ctx_limit(self) -> int:
        try:
            return max(256, int(self.store.state.get("contextLimit") or 8192))
        except Exception:
            return 8192

    def _update_ctx(self):
        try:
            used = self._estimate_tokens()
            limit = self._ctx_limit()
            if used <= 0:
                self.ctx_label.setText("")
                self.ctx_label.setVisible(False)
                return
            self.ctx_label.setVisible(True)
            pct = int(used * 100 / max(1, limit))
            human = ("%.1fk" % (used / 1000.0)) if used >= 1000 else str(used)
            self.ctx_label.setText("%s/%dk · %d%%" % (human, limit // 1000, pct))
            if pct >= 100:
                self.ctx_label.setStyleSheet("color:#ef4444;border-color:#7f1d1d;")
                self.ctx_label.setToolTip("已经超出上下文上限，再发很可能失败或超慢；点一下可以裁剪")
            elif pct >= 85:
                self.ctx_label.setStyleSheet("color:#f59e0b;")
                self.ctx_label.setToolTip("快满了，建议点一下裁剪旧消息")
            else:
                self.ctx_label.setStyleSheet("")
                self.ctx_label.setToolTip("当前话题的大致上下文占用，点一下有用法")
        except Exception:
            pass

    def _ctx_menu(self):
        limit = self._ctx_limit()
        used = self._estimate_tokens()
        menu = QMenu(self)
        head = menu.addAction("已用 ≈ %d / %d tokens" % (used, limit))
        head.setEnabled(False)
        menu.addSeparator()
        menu.addAction("删掉最早的消息（腾地方）", lambda: self._trim_context())
        menu.addAction("新建话题继续", self.new_session)
        menu.addAction("清空这个话题", self.clear_session)
        menu.addSeparator()
        menu.addAction("改上下文上限…", self.open_params)
        menu.exec(self.ctx_label.mapToGlobal(QPoint(0, self.ctx_label.height() + 4)))

    def _trim_context(self, keep_ratio: float = 0.7) -> bool:
        """从最早的消息开始删，删到上限的 keep_ratio 以下；至少留下最近一问一答。"""
        session = self.store.active_session()
        messages = session.get("messages") or []
        if len(messages) <= 1:
            return False
        target = self._ctx_limit() * keep_ratio
        removed = 0
        while len(messages) > 1 and self._estimate_tokens(messages) > target:
            del messages[0]
            removed += 1
        # 删完之后开头如果是助手/工具消息，也去掉，免得历史不连贯
        while messages and messages[0].get("role") != "user":
            del messages[0]
            removed += 1
        if removed:
            self.store.touch(session)
            self.store.save()
            self.render_session()
            self.refresh_sessions()
            self.statusBar().showMessage("删掉了最早的 %d 条消息" % removed, 5000)
        return removed > 0

    def _check_context(self, extra_chars: int) -> bool:
        """发送前检查上下文；超了让用户决定。返回 True 表示继续发。"""
        limit = self._ctx_limit()
        used = self._estimate_tokens()
        total = used + int(extra_chars / 1.6)
        if total <= limit * 0.95:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("上下文快满了")
        box.setText("这个话题大约已经用了 %s tokens（上限 %s）。\n\n"
                    "继续发就是把这些全都塞给模型：可能直接报错，也可能要等很久。"
                    % ("%.1fk" % (total / 1000.0), "%.1fk" % (limit / 1000.0)))
        trim_btn = box.addButton("自动删掉最早的消息", QMessageBox.AcceptRole)
        send_btn = box.addButton("照样发送", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is trim_btn:
            self._trim_context()
            return True
        return box.clickedButton() is send_btn

    def refresh_sessions(self):
        keyword = self.search.text().strip().lower()
        self.session_list.blockSignals(True)
        self.session_list.clear()
        active = self.store.state["activeSessionId"]
        for s in self.store.sorted_sessions():
            snippet = ""
            if keyword:
                if keyword in (s.get("title") or "").lower():
                    snippet = "标题匹配"
                else:
                    for msg in s.get("messages") or []:
                        text = msg.get("content") or ""
                        if not isinstance(text, str):
                            text = json.dumps(text, ensure_ascii=False)
                        low = text.lower()
                        if keyword in low:
                            pos = low.find(keyword)
                            snippet = "…" + " ".join(
                                text[max(0, pos - 12):pos + 30].split()) + "…"
                            break
                    if not snippet:
                        continue
            item = QListWidgetItem(("📌 " if s.get("pinned") else "") + (s.get("title") or "未命名"))
            item.setData(Qt.UserRole, s["id"])
            tip = "%s · %d 条" % (s.get("title") or "", len(s.get("messages") or []))
            if snippet:
                tip += "\n" + snippet
            item.setToolTip(tip)
            self.session_list.addItem(item)
            if s["id"] == active:
                self.session_list.setCurrentItem(item)
        self.session_list.blockSignals(False)

    def _pick_session(self, item):
        sid = item.data(Qt.UserRole)
        if sid == self.store.state["activeSessionId"]:
            return
        self._abort_stream()
        self.store.state["activeSessionId"] = sid
        self.store.save()
        self.refresh_sessions()
        self.render_session()
        self.update_title()

    def _session_menu(self, pos: QPoint):
        item = self.session_list.itemAt(pos)
        if item is None:
            return
        self.session_list.setCurrentItem(item)
        sid = item.data(Qt.UserRole)
        s = self.store.session(sid)
        if s is None:
            return
        menu = QMenu(self)
        act_rename = menu.addAction("重命名")
        act_pin = menu.addAction("取消置顶" if s.get("pinned") else "置顶")
        menu.addSeparator()
        act_md = menu.addAction("导出为 Markdown…")
        act_json = menu.addAction("导出为 JSON…")
        menu.addSeparator()
        act_del = menu.addAction("删除话题")
        chosen = menu.exec(self.session_list.mapToGlobal(pos))
        if chosen == act_rename:
            self._rename_session()
        elif chosen == act_pin:
            s["pinned"] = not s.get("pinned")
            self.store.save()
            self.refresh_sessions()
        elif chosen == act_md:
            self.export_session(sid, "md")
        elif chosen == act_json:
            self.export_session(sid, "json")
        elif chosen == act_del:
            self._delete_session(sid)

    def export_session(self, sid: str, fmt: str):
        session = self.store.session(sid)
        if session is None:
            return
        safe = "".join(c for c in (session.get("title") or "话题")
                       if c not in '\\/:*?"<>|').strip() or "话题"
        default = str(Path.home() / (safe + (".md" if fmt == "md" else ".json")))
        filt = "Markdown (*.md)" if fmt == "md" else "JSON (*.json)"
        path, _ = QFileDialog.getSaveFileName(self, "导出话题", default, filt)
        if not path:
            return
        try:
            if fmt == "md":
                lines = ["# %s" % (session.get("title") or "话题"), ""]
                for msg in session.get("messages") or []:
                    role = msg.get("role")
                    if role == "user":
                        lines.append("## 我")
                        lines.append(msg.get("content") or "")
                        for att in msg.get("attachments") or []:
                            lines.append("- 附件：%s" % att.get("name"))
                    elif role == "assistant":
                        lines.append("## 助手")
                        if msg.get("reasoning"):
                            lines.append("> 思考：%s" % msg["reasoning"].replace("\n", " "))
                        lines.append(msg.get("content") or "")
                    lines.append("")
                Path(path).write_text("\n".join(lines), encoding="utf-8")
            else:
                Path(path).write_text(
                    json.dumps(session, ensure_ascii=False, indent=1), encoding="utf-8")
            QMessageBox.information(self, "导出", "已导出到：\n%s" % path)
        except Exception as exc:
            QMessageBox.warning(self, "导出", "失败：%s" % exc)

    def _rename_session(self):
        s = self.store.active_session()
        name, ok = QInputDialog.getText(self, "重命名话题", "标题：", text=s.get("title") or "")
        if ok and name.strip():
            s["title"] = name.strip()
            self.store.save()
            self.refresh_sessions()
            self.update_title()

    def _delete_session(self, sid):
        if QMessageBox.question(self, "删除话题", "删除后不可恢复，确定？") != QMessageBox.Yes:
            return
        self._abort_stream()
        self.store.delete_session(sid)
        self.store.save()
        self.refresh_sessions()
        self.render_session()
        self.update_title()

    def new_session(self):
        self._abort_stream()
        self.store.add_session()
        self.store.save()
        self.refresh_sessions()
        self.render_session()
        self.update_title()
        self.composer.setFocus()

    def clear_session(self):
        s = self.store.active_session()
        if not s.get("messages"):
            return
        if QMessageBox.question(self, "清空话题", "清空当前话题的所有消息？") != QMessageBox.Yes:
            return
        self._abort_stream()
        s["messages"] = []
        self.store.touch(s)
        self.store.save()
        self.refresh_sessions()
        self.render_session()

    # ----------------------------------------------------------- 顶栏

    def update_title(self):
        s = self.store.active_session()
        self.title_label.setText(s.get("title") or "新话题")
        self.setWindowTitle("%s — %s" % (s.get("title") or "新话题", APP_TITLE))

    def refresh_chip(self):
        cfg = self.store.active_config()
        if cfg and cfg.get("model"):
            host = cfg.get("model")
            self.cfg_chip.setText("%s ▾" % host)
            self.cfg_chip.setToolTip("%s\n%s" % (cfg.get("name"), cfg.get("baseUrl")))
        else:
            self.cfg_chip.setText("未配置 ▾")

    def _show_cfg_menu(self):
        menu = QMenu(self)
        active = self.store.state["activeId"]
        for cfg in self.store.state["configs"]:
            label = "%s%s" % ("✓ " if cfg["id"] == active else "   ", cfg.get("name") or "未命名")
            act = menu.addAction(label)
            act.setToolTip(cfg.get("model") or "")
            act.triggered.connect(lambda _=False, cid=cfg["id"]: self._activate_cfg(cid))
        menu.addSeparator()
        menu.addAction("API 设置…", self.open_settings)
        menu.exec(self.cfg_chip.mapToGlobal(QPoint(0, self.cfg_chip.height() + 4)))

    def _activate_cfg(self, cid: str):
        self.store.state["activeId"] = cid
        self.store.save()
        self.refresh_chip()
        self._detect_ctx()

    def open_settings(self):
        dlg = SettingsDialog(self.store, self)
        if dlg.exec() == QDialog.Accepted:
            self.refresh_chip()

    # ----------------------------------------------------------- 渲染

    def render_session(self):
        self.chat.clear()
        s = self.store.active_session()
        messages = s.get("messages") or []
        if not messages:
            self.chat.show_empty()
            return
        for idx, msg in enumerate(messages):
            role = msg.get("role")
            if role == "user":
                self.chat.add(Bubble(
                    "user", msg.get("content") or "",
                    attachments=msg.get("attachments") or [],
                    skill=msg.get("skill"),
                    on_edit=self._edit_message, on_delete=self._delete_from,
                    msg_index=idx,
                ))
            elif role == "assistant":
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning") or ""
                if not content and not reasoning and msg.get("tool_calls"):
                    names = ", ".join(c.get("function", {}).get("name", "?")
                                      for c in msg["tool_calls"])
                    self.chat.add(ToolLine("🔧 调用工具：%s" % names))
                    continue
                bubble = Bubble("assistant", content,
                                attachments=msg.get("attachments") or [],
                                on_run=self.run_html, on_speak=self.speak,
                                on_delete=self._delete_from, msg_index=idx,
                                on_regen=self._regenerate, on_continue=self._continue_reply)
                if reasoning and self.show_reasoning:
                    bubble.set_reasoning(reasoning)
                    bubble.reason_toggle.setChecked(False)
                self.chat.add(bubble)
            elif role == "tool":
                self.chat.add(ToolLine("   ↳ %s" % _short(msg.get("content") or "", 200)))
        self.chat._follow = True
        QTimer.singleShot(30, lambda: self.chat.to_bottom(force=True))
        QTimer.singleShot(220, lambda: self.chat.to_bottom(force=True))
        self._update_ctx()

    # ----------------------------------------------------------- 消息编辑

    def _edit_message(self, index: int):
        try:
            session = self.store.active_session()
            messages = session.get("messages") or []
            if not (0 <= index < len(messages)):
                return
            msg = messages[index]
            if msg.get("role") != "user":
                return
            if self.thread is not None:
                QMessageBox.information(self, "编辑", "先等当前回答结束或停止。")
                return
            del messages[index:]
            self.store.touch(session)
            self.store.save()
            self.attachments = list(msg.get("attachments") or [])
            self._refresh_attachments()
            self.composer.setPlainText(msg.get("content") or "")
            self.render_session()
            self.refresh_sessions()
            self.composer.setFocus()
        except Exception as exc:
            QMessageBox.warning(self, "编辑", "出错了：%s" % exc)

    def _delete_from(self, index: int):
        try:
            session = self.store.active_session()
            messages = session.get("messages") or []
            if not (0 <= index < len(messages)):
                return
            if self.thread is not None:
                QMessageBox.information(self, "删除", "先等当前回答结束或停止。")
                return
            if QMessageBox.question(self, "删除消息",
                                    "删除这条及之后的所有消息？") != QMessageBox.Yes:
                return
            del messages[index:]
            self.store.touch(session)
            self.store.save()
            self.render_session()
            self.refresh_sessions()
        except Exception as exc:
            QMessageBox.warning(self, "删除", "出错了：%s" % exc)

    # ----------------------------------------------------------- 重新生成 / 继续

    def _regenerate(self, index: int):
        """丢掉这条回答，用同样的上下文再问一次。"""
        try:
            if self.thread is not None:
                return
            session = self.store.active_session()
            messages = session.get("messages") or []
            if not (0 <= index < len(messages)):
                return
            if messages[index].get("role") != "assistant":
                return
            if index < len(messages) - 1:
                # 不是最后一条：后面的对话会被一起丢掉，先说清楚
                if QMessageBox.question(
                        self, "重新生成",
                        "这条后面还有 %d 条消息，重新生成会把它们一起删掉。继续？"
                        % (len(messages) - index - 1)) != QMessageBox.Yes:
                    return
            del messages[index:]
            self.store.touch(session)
            self.store.save()
            self.render_session()
            self._ask(session, None, history=messages)
        except Exception as exc:
            QMessageBox.warning(self, "重新生成", "出错了：%s" % exc)

    def _continue_reply(self, index: int):
        """接在这条回答后面继续写，写完全并回同一条回答。"""
        try:
            if self.thread is not None:
                return
            session = self.store.active_session()
            messages = session.get("messages") or []
            if not (0 <= index < len(messages)):
                return
            msg = messages[index]
            if msg.get("role") != "assistant":
                return
            partial = (msg.get("content") or "").rstrip()
            if not partial:
                return
            self._append_index = index
            self._ask(session, None, continue_from=partial)
        except Exception as exc:
            self._append_index = None
            QMessageBox.warning(self, "继续", "出错了：%s" % exc)

    def _ask(self, session, user_index, continue_from=None, history=None):
        """按给定历史发起一次请求；history 不给就用整个会话。"""
        workers.purge()
        cfg = self.store.active_config()
        if cfg is None or not cfg.get("model"):
            QMessageBox.information(self, APP_TITLE, "先在设置里填模型名。")
            return
        request_messages = []
        sys_text = (session.get("system") or self.store.state.get("system") or "").strip()
        if sys_text:
            request_messages.append({"role": "system", "content": sys_text})
        base = history if history is not None else (session.get("messages") or [])
        request_messages.extend(dict(m) for m in base)
        if continue_from:
            request_messages.append({"role": "assistant", "content": continue_from})
            request_messages.append({"role": "user",
                                     "content": "请从刚才停顿的地方接着写完，不要重复已经写过的内容。"})

        self.bubble = Bubble("assistant", "", on_run=self.run_html, on_speak=self.speak,
                             on_regen=self._regenerate, on_continue=self._continue_reply)
        self.chat.add(self.bubble)
        self._acc = ""
        self._reason = ""
        self._timer_start = time.time()

        self._apply_custom_tools()
        self._stream_session = session["id"]
        self.thread = ChatThread(cfg, request_messages,
                                 self.store.state.get("params") or {}, self)
        self.thread.delta.connect(self._on_delta)
        self.thread.reasoning.connect(self._on_reasoning)
        self.thread.tool.connect(self._on_tool)
        self.thread.toolResult.connect(self._on_tool_result)
        self.thread.note.connect(self._on_note)
        self.thread.failed.connect(self._on_failed)
        self.thread.finished.connect(self._on_done)
        self.set_busy(True)
        self.thread.start()

    def run_html(self, code: str, lang: str = "html"):
        """运行 HTML / SVG 预览（窗口复用，不反复重建 WebEngine）。"""
        content = code
        if lang in ("html", "htm") and "<html" not in content.lower():
            content = ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
                       "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                       "<title>预览</title></head><body>" + code + "</body></html>")
        try:
            if self.store.state.get("previewExternal"):
                widgets.PreviewWindow(content, "网页预览")._open_external()
                return
            if self.preview_window is None:
                self.preview_window = widgets.PreviewWindow(content, "网页预览")
            if self.preview_window.view is None:
                widgets.PreviewWindow(content, "网页预览")._open_external()
                return
            self.preview_window.set_content(content)
            self.preview_window.show()
            self.preview_window.raise_()
            self.preview_window.activateWindow()
        except Exception as exc:
            QMessageBox.warning(self, "预览", "打开预览失败：%s" % exc)

    # ----------------------------------------------------------- 快捷指令

    COMMANDS = [
        ("/new", "新建话题", "new_session"),
        ("/clear", "清空当前话题", "clear_session"),
        ("/stop", "停止生成", "stop"),
        ("/regen", "重新生成最后一条回答", "_cmd_regen"),
        ("/cont", "继续写最后一条回答", "_cmd_continue"),
        ("/sys", "设置本话题的系统提示词", "open_session_system"),
        ("/skills", "技能库", "open_skills"),
        ("/params", "对话参数", "open_params"),
        ("/image", "画图", "open_image"),
        ("/compare", "模型对比", "open_compare"),
        ("/export", "导出本话题为 Markdown", "_cmd_export"),
        ("/help", "看所有指令", "_cmd_help"),
    ]

    def run_command(self, text: str):
        name = text.split()[0].lower()
        table = {cmd[0]: cmd[2] for cmd in self.COMMANDS}
        target = table.get(name)
        if target is None:
            self._cmd_help("没有这个指令：%s" % name)
            return
        if target.startswith("_cmd_"):
            getattr(self, target)()
        else:
            getattr(self, target)()

    def _cmd_help(self, extra: str = ""):
        lines = [("%-9s %s" % (name, desc)) for name, desc, _ in self.COMMANDS]
        head = (extra + "\n\n") if extra else ""
        QMessageBox.information(self, "指令", head + "\n".join(lines))

    def _cmd_regen(self):
        session = self.store.active_session()
        messages = session.get("messages") or []
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                self._regenerate(i)
                return
        QMessageBox.information(self, "重新生成", "这个话题还没有回答可以重来。")

    def _cmd_continue(self):
        session = self.store.active_session()
        messages = session.get("messages") or []
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                self._continue_reply(i)
                return
        QMessageBox.information(self, "继续", "这个话题还没有回答可以接着写。")

    def _cmd_export(self):
        self.export_session(self.store.state["activeSessionId"], "md")

    def open_session_system(self):
        session = self.store.active_session()
        current = session.get("system") or ""
        text, ok = QInputDialog.getMultiLineText(
            self, "本话题系统提示词",
            "只对这个话题生效；留空就用全局设置。", current)
        if not ok:
            return
        if text.strip():
            session["system"] = text.strip()
        else:
            session.pop("system", None)
        self.store.save()
        self._update_ctx()

    # ----------------------------------------------------------- 发送

    def send(self):
        if self.thread is not None:
            return
        self._append_index = None
        text = self.composer.toPlainText().strip()
        if text.startswith("/"):
            self.composer.clear()
            self.run_command(text)
            return
        if not text and not self.attachments:
            return
        extra = len(text) + sum(len(a.get("text") or "") for a in self.attachments)
        if not self._check_context(extra):
            return
        cfg = self.store.active_config()
        if cfg is None or not cfg.get("baseUrl"):
            self.open_settings()
            return
        if not cfg.get("model"):
            QMessageBox.information(self, APP_TITLE, "先在设置里填模型名。")
            self.open_settings()
            return

        atts = list(self.attachments)
        skill = dict(self.active_skill) if self.active_skill else None

        s = self.store.active_session()
        message = {"role": "user", "content": text}
        if atts:
            message["attachments"] = atts
        if skill:
            message["skill"] = {"emoji": skill.get("emoji", "✨"), "name": skill.get("name", "")}
        s["messages"].append(message)
        if (s.get("title") or "") in ("", "新话题"):
            s["title"] = _short(text or (atts[0].get("name") if atts else "新话题"), 18)
        self.store.touch(s)
        self.store.save()

        self.chat.remove_empty()
        self.chat.add(Bubble("user", text, attachments=atts, skill=skill))
        self.composer.clear()
        self.attachments = []
        self._refresh_attachments()
        self.refresh_sessions()
        self.update_title()

        self.bubble = Bubble("assistant", "", on_run=self.run_html, on_speak=self.speak,
                             on_regen=self._regenerate, on_continue=self._continue_reply)
        self.chat.add(self.bubble)
        self._acc = ""
        self._reason = ""

        request_messages = []
        sys_text = (s.get("system") or self.store.state.get("system") or "").strip()
        if sys_text:
            request_messages.append({"role": "system", "content": sys_text})
        if skill and skill.get("prompt"):
            request_messages.append({"role": "system", "content": skill["prompt"]})
        request_messages.extend(dict(m) for m in s["messages"])

        self._apply_custom_tools()
        self._stream_session = s["id"]
        self._timer_start = time.time()
        self.thread = ChatThread(cfg, request_messages,
                                 self.store.state.get("params") or {}, self)
        self.thread.delta.connect(self._on_delta)
        self.thread.reasoning.connect(self._on_reasoning)
        self.thread.tool.connect(self._on_tool)
        self.thread.toolResult.connect(self._on_tool_result)
        self.thread.note.connect(self._on_note)
        self.thread.failed.connect(self._on_failed)
        self.thread.finished.connect(self._on_done)
        self.set_busy(True)
        self.thread.start()

    def stop(self):
        self.stop_speaking()
        if self.thread is not None:
            self.thread.stop()

    def set_busy(self, busy: bool):
        self.send_btn.setVisible(not busy)
        self.stop_btn.setVisible(busy)
        self.composer.setReadOnly(False)

    def _schedule(self):
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _flush_render(self):
        if _alive(self.bubble):
            self.bubble.set_text(self._acc)
            self.chat.to_bottom()

    def _on_delta(self, chunk: str):
        self._acc += chunk
        self._schedule()

    def _on_reasoning(self, chunk: str):
        self._reason += chunk
        if _alive(self.bubble):
            self.bubble.set_reasoning(self._reason)

    def _on_tool(self, name: str, args: str):
        if _alive(self.bubble):
            self.bubble.set_tool(name, args)

    def _on_tool_result(self, name: str, result: str):
        if _alive(self.bubble):
            self.bubble.add_tool_result(name, result)

    def _on_note(self, text: str):
        self.statusBar().showMessage(text, 4000)

    def _on_failed(self, message: str):
        self._flush_render()
        if not _alive(self.bubble):
            return
        if not self._acc.strip():
            self.bubble.view_error(message)
        else:
            self.bubble.set_text(self._acc + "\n\n> ⚠️ 中断：%s" % _short(message, 200))

    def _abort_stream(self):
        """换话题/清空/关窗口前先收尾，别让还在跑的流去碰已经销毁的控件。"""
        self._render_timer.stop()
        if self.thread is not None:
            self.thread.stop()
        self.bubble = None
        self._append_index = None

    def _on_done(self):
        self._render_timer.stop()
        self._flush_render()
        sid = self._stream_session
        s = self.store.session(sid) if sid else None
        if s is None:
            s = self.store.active_session()
        cancelled = self.thread is not None and self.thread.streamer is not None \
            and self.thread.streamer.cancelled

        # 统计：用时 / 字数 / 速度
        elapsed = max(0.001, time.time() - getattr(self, "_timer_start", time.time()))
        chars = len(self._acc.strip())
        stats = ""
        if chars:
            stats = "%.1f 秒 · %d 字 · %.1f 字/秒" % (elapsed, chars, chars / elapsed)
            if cancelled:
                stats = "已停止 · " + stats

        append_index = getattr(self, "_append_index", None)
        self._append_index = None
        if append_index is not None and 0 <= append_index < len(s["messages"]):
            # 「继续」：并回原来那条回答，而不是另起一条
            msg = s["messages"][append_index]
            merged = (msg.get("content") or "").rstrip() + self._acc
            msg["content"] = merged + ("\n\n_（已停止）_" if cancelled else "")
            if self._reason:
                msg["reasoning"] = (msg.get("reasoning") or "") + self._reason
            if _alive(self.bubble):
                self.bubble.set_text(merged)
                self.bubble.msg_index = append_index
                if stats:
                    self.bubble.set_stats(stats)
                self.bubble.finish(append_index)
        elif self._acc.strip() or self._reason.strip():
            s["messages"].append({
                "role": "assistant",
                "content": self._acc,
                "reasoning": self._reason,
            })
            if cancelled:
                s["messages"][-1]["content"] = self._acc + "\n\n_（已停止）_"
            if _alive(self.bubble):
                if stats:
                    self.bubble.set_stats(stats)
                self.bubble.finish(len(s["messages"]) - 1)

        self.store.touch(s)
        self.store.save()
        answer = self._acc
        if self.thread is not None:
            workers.retire(self.thread)
        self.thread = None
        self.bubble = None
        self.set_busy(False)
        self.refresh_sessions()
        self._update_ctx()
        self.composer.setFocus()
        if self.auto_speak and answer.strip():
            self.speak(answer)

    # ----------------------------------------------------------- 关闭

    def closeEvent(self, event):
        self._closing = True
        self._render_timer.stop()
        self.bubble = None
        try:
            self.stop_speaking()
        except Exception:
            pass
        if self.thread is not None:
            self.thread.stop()
            if not self.thread.wait(5000):
                self.thread.terminate()
                self.thread.wait(1000)
        # 预览窗口里是 WebEngine，先把页面停掉再退，否则销毁时容易崩
        if self.preview_window is not None:
            try:
                self.preview_window.shutdown()
            except Exception:
                pass
            self.preview_window = None
            for _ in range(10):
                QApplication.processEvents()
        g = self.geometry()
        self.store.state["geometry"] = [g.x(), g.y(), g.width(), g.height()]
        try:
            self.store.save()
        except Exception:
            pass
        super().closeEvent(event)


def selftest() -> int:
    """打包后的自检：连一次接口、发一句话、把结果写进 selftest.log。

    用法：自用API终端.exe --selftest
    环境变量：SELFAPI_BASE（默认本机 18899）、SELFAPI_MODEL（默认 fake-model）
    """
    import time

    base = os.environ.get("SELFAPI_BASE", "http://127.0.0.1:18899/v1")
    model = os.environ.get("SELFAPI_MODEL", "fake-model")
    log_path = store.data_dir() / "selftest.log"
    lines = ["selftest  base=%s  model=%s" % (base, model)]

    def write(ok: bool, text: str):
        lines.append("answer=%r" % text)
        lines.append("RESULT=%s" % ("PASS" if ok else "FAIL"))
        try:
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass

    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setStyleSheet(theme.QSS)
        win = MainWindow()
        win.show()
        cfg = win.store.active_config()
        cfg.update({"name": "自检", "baseUrl": base, "apiKey": "sk-test", "model": model})
        win.store.save()
        win.refresh_chip()
        app.processEvents()

        win.composer.setPlainText("你好，测试一下")
        win.send()

        deadline = time.time() + 40
        while time.time() < deadline and win.thread is not None:
            app.processEvents()
            time.sleep(0.05)
        app.processEvents()

        text = ""
        for msg in win.store.active_session()["messages"]:
            if msg.get("role") == "assistant":
                text = msg.get("content") or ""
        ok = "测试模型" in text
        write(ok, text)
        win.close()
        app.processEvents()
        return 0 if ok else 1
    except Exception:
        lines.append(traceback.format_exc())
        write(False, "")
        return 1


def selftest_preview() -> int:
    """打包后自检：确认 QtWebEngine 预览真的能渲染。结果写 selftest-preview.log。"""
    import time

    log_path = store.data_dir() / "selftest-preview.log"
    lines = ["preview selftest"]
    try:
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setStyleSheet(theme.QSS)
        win = widgets.PreviewWindow(
            "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
            "<body><h1>预览自检 OK</h1></body></html>", "预览自检")
        win.load()
        win.show()

        text = {"v": None}
        deadline = time.time() + 12
        asked = False
        while time.time() < deadline:
            app.processEvents()
            time.sleep(0.05)
            if not asked and win.view is not None and time.time() > deadline - 10:
                asked = True
                win.view.page().runJavaScript(
                    "document.body.innerText", 0,
                    lambda v: text.__setitem__("v", v))
            if text["v"]:
                break
        ok = bool(text["v"]) and "预览自检" in (text["v"] or "")
        lines.append("dom=%r" % text["v"])
        lines.append("RESULT=%s" % ("PASS" if ok else "FAIL"))
        win.close()
        app.processEvents()
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0 if ok else 1
    except Exception:
        lines.append(traceback.format_exc())
        lines.append("RESULT=FAIL")
        try:
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass
        return 1


def install_crash_log():
    """把 Python 异常和致命错误写进 crash.log，闪退也有据可查。"""
    import faulthandler
    import threading
    import time
    import traceback

    try:
        handle = open(store.data_dir() / "crash.log", "a", buffering=1, encoding="utf-8")
    except Exception:
        return
    try:
        faulthandler.enable(file=handle, all_threads=True)
    except Exception:
        pass

    def hook(exc_type, exc, tb):
        try:
            handle.write("\n=== %s  异常\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            traceback.print_exception(exc_type, exc, tb, file=handle)
            handle.flush()
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook

    def thread_hook(args):
        try:
            handle.write("\n=== %s  线程异常\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            traceback.print_exception(args.exc_type, args.exc_value,
                                      args.exc_traceback, file=handle)
            handle.flush()
        except Exception:
            pass

    threading.excepthook = thread_hook


def main() -> int:
    if "--selftest-preview" in sys.argv:
        return selftest_preview()
    if "--selftest" in sys.argv:
        return selftest()
    install_crash_log()
    try:
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_TITLE)
    app.setStyleSheet(theme.QSS)
    icon = res_path("icon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    win = MainWindow()
    win.show()
    code = app.exec()
    # 退出前把东西按顺序拆干净：线程等停 → 回收 → 显式销毁窗口 → 排空事件。
    # 直接让解释器在退出时顺手销毁窗口，会偶发 0xc0000005。
    workers.shutdown(2000)
    workers.purge()
    try:
        win.deleteLater()
    except Exception:
        pass
    for _ in range(8):
        app.processEvents()
    return code


if __name__ == "__main__":
    sys.exit(main())
