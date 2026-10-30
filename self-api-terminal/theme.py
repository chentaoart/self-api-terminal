# -*- coding: utf-8 -*-
"""配色与样式表。"""

BG = "#0a0a0f"
PANEL = "#111118"
PANEL2 = "#17171f"
LINE = "#24242e"
TEXT = "#e9e9f0"
MUTED = "#8888a0"
ACCENT = "#a78bfa"
ACCENT_DARK = "#7c3aed"
OK = "#4ade80"
ERR = "#f87171"
WARN = "#fbbf24"
THINK = "#7dd3fc"

QSS = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 10.5pt;
}}
QToolTip {{
    background-color: {PANEL2};
    color: {TEXT};
    border: 1px solid {LINE};
    padding: 4px 8px;
}}

/* ---------- 侧边栏 ---------- */
QFrame#sidebar {{
    background-color: #0e0e14;
    border-right: 1px solid {LINE};
}}
QLabel#brand {{
    font-size: 12pt;
    font-weight: 700;
    color: #ffffff;
}}
QLabel#brandMark {{
    background-color: {ACCENT_DARK};
    border-radius: 9px;
    color: white;
    font-weight: 800;
    font-size: 12pt;
}}
QPushButton#newChat {{
    background-color: #201a33;
    border: 1px solid #3b2f5e;
    border-radius: 9px;
    padding: 8px 10px;
    color: #d9ccff;
    font-weight: 600;
}}
QPushButton#newChat:hover {{
    background-color: #2b2145;
    border-color: {ACCENT};
    color: #ffffff;
}}
QLineEdit#search {{
    background-color: #0a0a10;
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 6px 9px;
    color: {TEXT};
    font-size: 9.5pt;
}}
QLineEdit#search:focus {{ border-color: #4c4c66; }}

QListWidget#sessions {{
    background: transparent;
    border: none;
    outline: none;
    padding: 2px 4px;
}}
QListWidget#sessions::item {{
    background: transparent;
    border-radius: 8px;
    padding: 8px 9px;
    color: #cfcfdb;
}}
QListWidget#sessions::item:hover {{ background-color: {PANEL2}; }}
QListWidget#sessions::item:selected {{
    background-color: #221a38;
    color: #ffffff;
}}

/* ---------- 顶栏 ---------- */
QFrame#header {{
    background-color: {BG};
    border-bottom: 1px solid {LINE};
}}
QLabel#pageTitle {{
    font-size: 11pt;
    font-weight: 600;
}}
QPushButton#cfgChip {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 4px 8px;
    color: {MUTED};
    font-family: Consolas, "Microsoft YaHei UI";
    font-size: 9.5pt;
}}
QPushButton#cfgChip:hover {{
    background-color: {PANEL2};
    border-color: {LINE};
    color: #d6d6e2;
}}
QPushButton#iconBtn {{
    background-color: transparent;
    border: 1px solid {LINE};
    border-radius: 8px;
    color: {MUTED};
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    font-size: 13pt;
}}
QPushButton#iconBtn:hover {{
    background-color: {PANEL2};
    border-color: #3d3d52;
    color: #ffffff;
}}
QPushButton#iconBtn:checked {{
    background-color: #17283a;
    border-color: {THINK};
    color: {THINK};
}}

/* ---------- 聊天区 ---------- */
QScrollArea#chat {{ background: transparent; border: none; }}
QWidget#chatBody {{ background: transparent; }}

QTextBrowser#msgText {{
    background: transparent;
    border: none;
    color: {TEXT};
    selection-background-color: #4c3a86;
}}
QFrame#userBubble {{
    background-color: #191922;
    border: 1px solid {LINE};
    border-radius: 13px;
}}

QLabel#avatarA {{
    background-color: {ACCENT_DARK};
    border-radius: 9px;
    color: white;
    font-weight: 700;
    font-size: 10pt;
}}
QLabel#avatarU {{
    background-color: #1d1d27;
    border: 1px solid {LINE};
    border-radius: 9px;
    color: {MUTED};
    font-size: 9pt;
}}
QPushButton#ghost {{
    background: transparent;
    border: none;
    color: #5f5f78;
    font-size: 9pt;
    padding: 2px 6px;
    border-radius: 6px;
}}
QPushButton#ghost:hover {{ background-color: {PANEL2}; color: #cfcfdb; }}

QToolButton#reasonToggle {{
    background: transparent;
    border: none;
    color: #6f8fa8;
    font-size: 9pt;
    padding: 2px 0;
    text-align: left;
}}
QToolButton#reasonToggle:hover {{ color: {THINK}; }}
QTextBrowser#reasonText {{
    background-color: #0c1418;
    border: 1px solid #1d2f38;
    border-radius: 8px;
    color: #9fc4d8;
    font-size: 9.5pt;
}}

QLabel#toolLine {{
    color: #8b8ba5;
    font-size: 9pt;
    font-family: Consolas, "Microsoft YaHei UI";
}}

/* ---------- 输入区 ---------- */
QFrame#composer {{
    background-color: {PANEL};
    border: 1px solid {LINE};
    border-radius: 13px;
}}
QPlainTextEdit#input {{
    background: transparent;
    border: none;
    color: {TEXT};
    padding: 9px 4px;
    selection-background-color: #4c3a86;
}}
QPushButton#send {{
    background-color: {ACCENT_DARK};
    border: none;
    border-radius: 17px;
    color: white;
    font-size: 13pt;
    min-width: 34px; max-width: 34px;
    min-height: 34px; max-height: 34px;
}}
QPushButton#send:hover {{ background-color: #8b4cf0; }}
QPushButton#send:disabled {{ background-color: #2a2a38; color: #5f5f78; }}
QPushButton#sendStop {{
    background-color: #7f1d1d;
    border: none;
    border-radius: 17px;
    color: white;
    font-size: 12pt;
    min-width: 34px; max-width: 34px;
    min-height: 34px; max-height: 34px;
}}
QPushButton#sendStop:hover {{ background-color: #b91c1c; }}
QLabel#hint {{ color: #4d4d63; font-size: 8.5pt; }}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: #262633;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background-color: #33334a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- 对话框 ---------- */
QDialog {{ background-color: {BG}; }}
QFrame#dialogPanel {{
    background-color: {PANEL};
    border: 1px solid {LINE};
    border-radius: 14px;
}}
QLabel#fieldLabel {{ color: {MUTED}; font-size: 9.5pt; }}
QLineEdit, QComboBox {{
    background-color: #0b0b11;
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 7px 9px;
    color: {TEXT};
    selection-background-color: #4c3a86;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT_DARK}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background-color: {PANEL2};
    border: 1px solid {LINE};
    selection-background-color: #2b2145;
    color: {TEXT};
    outline: none;
}}
QListWidget#cfgList {{
    background-color: #0d0d14;
    border: 1px solid {LINE};
    border-radius: 9px;
    outline: none;
}}
QListWidget#cfgList::item {{ padding: 8px 9px; border-radius: 7px; color: #cfcfdb; }}
QListWidget#cfgList::item:selected {{ background-color: #221a38; color: white; }}
QPushButton#primary {{
    background-color: {ACCENT_DARK};
    border: none;
    border-radius: 9px;
    padding: 8px 16px;
    color: white;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background-color: #8b4cf0; }}
QPushButton#ghostBtn {{
    background-color: transparent;
    border: 1px solid {LINE};
    border-radius: 9px;
    padding: 7px 14px;
    color: #c9c9d8;
}}
QPushButton#ghostBtn:hover {{ background-color: {PANEL2}; border-color: #3d3d52; }}
QPushButton#linkBtn {{
    background: transparent; border: none; color: {ACCENT}; padding: 3px 6px;
}}
QPushButton#linkBtn:hover {{ color: #d9ccff; }}
QLabel#status {{ font-size: 9.5pt; color: {MUTED}; }}

QMenu {{
    background-color: {PANEL2};
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 5px;
}}
QMenu::item {{
    padding: 7px 22px 7px 12px;
    border-radius: 7px;
    color: #d6d6e2;
}}
QMenu::item:selected {{ background-color: #2b2145; color: white; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}

QPushButton#skillChip {{
    background-color: #14141d;
    border: 1px solid {LINE};
    border-radius: 11px;
    padding: 3px 10px;
    color: #b9b9cc;
    font-size: 9pt;
}}
QPushButton#skillChip:hover {{
    border-color: #4c4c66;
    color: #ffffff;
}}
QPushButton#skillChip:checked {{
    background-color: #221a38;
    border-color: {ACCENT_DARK};
    color: #e9d5ff;
}}

QLabel#stats {{
    color: #6b6b85;
    font-size: 8.5pt;
    padding-left: 6px;
}}

QPushButton#ctxChip {{
    color: #6b6b85;
    background-color: transparent;
    border: 1px solid {LINE};
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 8.5pt;
}}
QPushButton#ctxChip:hover {{
    border-color: #4c4c66;
    color: #d6d6e2;
}}
"""
