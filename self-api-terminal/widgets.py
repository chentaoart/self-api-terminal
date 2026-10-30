# -*- coding: utf-8 -*-
"""附件、图片查看、网页预览这些小部件。"""

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

import media

# WebEngine 故意不在这里 import：它一加载就会初始化内核（还会起子进程），
# 不用「运行」预览的会话完全没必要付这个代价，出了问题也更容易隔离。
QWebEngineView = None
_engine_tried = False


def load_engine():
    """真正需要预览时才把 QtWebEngine 拉起来。"""
    global QWebEngineView, _engine_tried
    if _engine_tried:
        return QWebEngineView
    _engine_tried = True
    if os.environ.get("SELFAPI_NO_WEBENGINE"):
        return None
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView as View
        QWebEngineView = View
    except Exception:
        QWebEngineView = None
    return QWebEngineView


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ImageViewer(QDialog):
    """点缩略图看大图。"""

    def __init__(self, att: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(att.get("name") or "图片")
        self.setStyleSheet("background:#0a0a0f;")
        screen = QGuiApplication.primaryScreen().availableGeometry()
        max_w, max_h = int(screen.width() * 0.82), int(screen.height() * 0.82)

        path = att.get("path") or ""
        pix = QPixmap(path)
        if pix.isNull():
            text = "图片读不出来：%s" % path
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel(text))
            self.resize(420, 160)
            return

        w, h = pix.width(), pix.height()
        scale = min(1.0, max_w / max(w, 1), max_h / max(h, 1))
        shown = pix.scaled(int(w * scale), int(h * scale), Qt.KeepAspectRatio,
                           Qt.SmoothTransformation)

        label = QLabel()
        label.setPixmap(shown)
        label.setAlignment(Qt.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll, 1)

        bar = QFrame()
        bar.setStyleSheet("background:#111118;border-top:1px solid #24242e;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 6, 10, 6)
        info = QLabel("%s · %d×%d · %s" % (att.get("name") or "", w, h,
                                           media.summarize(att).split(" · ")[-1]))
        info.setStyleSheet("color:#8888a0;")
        bl.addWidget(info, 1)
        open_btn = QPushButton("用系统看图打开")
        open_btn.setObjectName("ghostBtn")
        open_btn.clicked.connect(lambda: os.startfile(path))
        bl.addWidget(open_btn)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("ghostBtn")
        close_btn.clicked.connect(self.accept)
        bl.addWidget(close_btn)
        layout.addWidget(bar)

        self.resize(min(shown.width(), max_w) + 4, min(shown.height(), max_h) + 56)


class ImageThumb(ClickableLabel):
    """消息里的图片缩略图。"""

    def __init__(self, att: dict, parent=None, max_w: int = 280, max_h: int = 200):
        super().__init__(parent)
        self.att = att
        pix = QPixmap(att.get("path") or "")
        if pix.isNull():
            self.setText("🖼 图片（已丢失）")
            self.setStyleSheet("color:#f87171;")
            return
        scale = min(1.0, max_w / max(pix.width(), 1), max_h / max(pix.height(), 1))
        shown = pix.scaled(int(pix.width() * scale), int(pix.height() * scale),
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(shown)
        self.setToolTip("%s（点击看大图）" % (att.get("name") or ""))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("border:1px solid #24242e;border-radius:8px;")
        self.clicked.connect(self._open)

    def _open(self):
        ImageViewer(self.att, self.window()).exec()


class FileChip(QFrame):
    """消息里的文件标签。"""

    def __init__(self, att: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame{background:#15151f;border:1px solid #24242e;"
                           "border-radius:8px;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 5, 10, 5)
        lay.setSpacing(7)
        icon = QLabel("📄")
        lay.addWidget(icon)
        name = QLabel(media.summarize(att))
        name.setStyleSheet("color:#c9c9d8;")
        lay.addWidget(name)


class AttachChip(QFrame):
    """输入框上方的待发送附件。"""

    removed = Signal(object)

    def __init__(self, att: dict, parent=None):
        super().__init__(parent)
        self.att = att
        self.setStyleSheet("QFrame{background:#17171f;border:1px solid #2b2b3a;"
                           "border-radius:9px;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(7, 4, 5, 4)
        lay.setSpacing(6)

        if att.get("kind") == "image":
            pix = QPixmap(att.get("path") or "")
            thumb = QLabel()
            if not pix.isNull():
                thumb.setPixmap(pix.scaled(26, 26, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation))
            else:
                thumb.setText("🖼")
            lay.addWidget(thumb)
        else:
            lay.addWidget(QLabel("📄"))

        label = QLabel(att.get("name") or "附件")
        label.setMaximumWidth(150)
        label.setStyleSheet("color:#c9c9d8;")
        label.setToolTip(media.summarize(att))
        lay.addWidget(label)

        close = QPushButton("✕")
        close.setFixedSize(18, 18)
        close.setCursor(Qt.PointingHandCursor)
        close.setStyleSheet("QPushButton{background:transparent;border:none;color:#6b6b85;}"
                            "QPushButton:hover{color:#fff;}")
        close.clicked.connect(lambda: self.removed.emit(self.att))
        lay.addWidget(close)


class AttachmentBar(QWidget):
    removed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 4)
        self.layout_.setSpacing(6)
        self.setVisible(False)

    def set_items(self, atts):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for att in atts:
            chip = AttachChip(att)
            chip.removed.connect(self.removed.emit)
            self.layout_.addWidget(chip)
        self.layout_.addStretch(1)
        self.setVisible(bool(atts))


class PreviewWindow(QDialog):
    """运行 HTML / SVG 的预览窗口。"""

    def __init__(self, content: str, title: str = "网页预览", parent=None):
        super().__init__(parent)
        self.content = content
        self.setWindowTitle(title)
        self.resize(940, 720)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setModal(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QFrame()
        bar.setStyleSheet("background:#111118;border-bottom:1px solid #24242e;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 6, 10, 6)
        name = QLabel(title)
        name.setStyleSheet("color:#c9c9d8;font-weight:600;")
        bl.addWidget(name, 1)
        reload_btn = QPushButton("重新运行")
        reload_btn.setObjectName("ghostBtn")
        reload_btn.clicked.connect(self._load)
        bl.addWidget(reload_btn)
        browser_btn = QPushButton("在浏览器打开")
        browser_btn.setObjectName("ghostBtn")
        browser_btn.clicked.connect(self._open_external)
        bl.addWidget(browser_btn)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("ghostBtn")
        close_btn.clicked.connect(self.accept)
        bl.addWidget(close_btn)
        layout.addWidget(bar)

        self.view = None
        self._loaded = False
        view_class = load_engine()
        if view_class is not None:
            try:
                # 不设父控件：WebEngine 的页面生命周期比普通 QWidget 麻烦，
                # 让 Qt 自己管，窗口复用（见 set_content），避免反复建/销毁页面。
                self.view = view_class()
                self.view.loadFinished.connect(self._on_loaded)
                layout.addWidget(self.view, 1)
            except Exception:
                self.view = None
        if self.view is None:
            hint = QLabel("这个环境没有启用内嵌浏览器，可以点右上「在浏览器打开」。")
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet("color:#8888a0;padding:30px;")
            layout.addWidget(hint, 1)

        QTimer.singleShot(7000, self._check_loaded)

    def set_content(self, content: str, title: str = "网页预览"):
        """复用同一个窗口：换内容，不重建 WebEngine 页面。"""
        self.content = content
        self.setWindowTitle(title)
        self._loaded = False
        self._load()

    def _on_loaded(self, ok: bool):
        self._loaded = bool(ok)
        if not ok:
            self._check_loaded()

    def _check_loaded(self):
        if self.view is not None and not self._loaded:
            self.setWindowTitle(self.windowTitle() + "（没加载出来？试试「在浏览器打开」）")

    def load(self):
        self._load()
        self.show()

    def _load(self):
        if self.view is not None:
            self.view.setHtml(self.content, QUrl("about:blank"))

    def _open_external(self):
        path = Path(tempfile.gettempdir()) / ("hermes-preview-%d.html" % os.getpid())
        path.write_text(self.content, encoding="utf-8")
        os.startfile(str(path))

    def shutdown(self):
        """退出前把页面停下来，别让 WebEngine 在销毁时还占着 profile。"""
        if self.view is not None:
            try:
                self.view.stop()
                self.view.setHtml("")
                self.view.deleteLater()
            except Exception:
                pass
            self.view = None
        self.hide()
