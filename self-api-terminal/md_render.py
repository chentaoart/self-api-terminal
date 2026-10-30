# -*- coding: utf-8 -*-
"""把 Markdown 渲染成 QTextDocument 能吃的 HTML（Qt 只支持 CSS 的一个子集）。"""

import html
import re

_CODE_BG = "#0d0d13"
_CODE_FG = "#d7d7e4"
_INLINE_BG = "#1e1e2a"

KEYWORDS = set("""
if else elif for while do switch case break continue return function def class new try
except catch finally throw raise import export from default this self super extends
implements static public private protected void int float str bool list dict set tuple
var let const typeof instanceof in of null nil undefined true false True False None
async await yield lambda pass print not and or is with as del global nonlocal assert
""".split())

_TOKEN = re.compile(
    r"(?P<comment>#[^\n]*|//[^\n]*)"
    r"|(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)"
    r"|(?P<number>\b\d+(?:\.\d+)?\b)"
    r"|(?P<word>[A-Za-z_]\w*)"
)


def _highlight(code: str) -> str:
    out = []
    last = 0
    for m in _TOKEN.finditer(code):
        out.append(html.escape(code[last:m.start()]))
        kind = m.lastgroup
        text = html.escape(m.group())
        if kind == "comment":
            out.append('<span style="color:#5f6b7a;font-style:italic">%s</span>' % text)
        elif kind == "string":
            out.append('<span style="color:#a6e3a1">%s</span>' % text)
        elif kind == "number":
            out.append('<span style="color:#fab387">%s</span>' % text)
        elif m.group() in KEYWORDS:
            out.append('<span style="color:#cba6f7">%s</span>' % text)
        else:
            out.append(text)
        last = m.end()
    out.append(html.escape(code[last:]))
    return "".join(out)


def _code_block(lang: str, code: str) -> str:
    code = code if code.strip() else " "
    body = _highlight(code) if lang.lower() not in ("text", "txt", "plain") else html.escape(code)
    label = ('<div style="color:#6b6b85;font-size:11px;margin:2px 0 2px 2px">' +
             html.escape(lang) + '</div>') if lang else ""
    return (
        '<table width="100%" cellpadding="9" cellspacing="0" '
        'style="margin-top:8px;margin-bottom:8px;background-color:' + _CODE_BG + ';">'
        '<tr><td style="background-color:' + _CODE_BG + ';">' + label +
        '<pre style="margin:0;color:' + _CODE_FG +
        ";font-family:Consolas,'Cascadia Mono',monospace;font-size:12px;line-height:1.5;\">" +
        body +
        '</pre></td></tr></table>'
    )


def _inline(text: str) -> str:
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`\n]+)`", keep, text)
    text = html.escape(text)

    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"~~([^~\n]+)~~", r"<s>\1</s>", text)
    text = re.sub(
        r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" style="color:#a78bfa">\1</a>',
        text,
    )
    text = re.sub(r"(?<![\"'>=])(https?://[^\s<>\u4e00-\u9fff]+)",
                  r'<a href="\1" style="color:#a78bfa">\1</a>', text)

    def restore(m):
        return ('<span style="background-color:%s;color:#a6e3a1;'
                'font-family:Consolas,monospace;font-size:12.5px">%s</span>'
                % (_INLINE_BG, html.escape(codes[int(m.group(1))])))

    return re.sub(r"\x00(\d+)\x00", restore, text)


def md_to_html(md: str) -> str:
    """渲染入口。任何渲染异常都退化成纯文本，绝不让界面卡住或崩掉。"""
    try:
        return _render_md(md)
    except Exception:
        return ('<pre style="white-space:pre-wrap;font-family:Consolas,monospace;'
                'font-size:12.5px;color:#d6d6e2;margin:4px 0;">' + html.escape(md or "") + '</pre>')


def _render_md(md: str) -> str:
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    list_stack: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph():
        if paragraph:
            body = "<br/>".join(_inline(x) for x in paragraph)
            out.append('<p style="margin:4px 0;line-height:1.62;">%s</p>' % body)
            paragraph.clear()

    def close_lists(upto: int | None = None):
        while list_stack and (upto is None or len(list_stack) > upto):
            out.append("</li></ul>" if list_stack.pop() == "ul" else "</li></ol>")

    while i < len(lines):
        line = lines[i]

        # 代码块
        if line.lstrip().startswith("```"):
            flush_paragraph()
            close_lists()
            lang = line.strip()[3:].strip()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append(_code_block(lang, "\n".join(buf)))
            continue

        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            close_lists()
            i += 1
            continue

        # 表格
        if stripped.startswith("|") and i + 1 < len(lines) \
                and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            flush_paragraph()
            close_lists()
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            cell = 'border:1px solid #24242e;padding:5px 9px;'
            parts = ['<table width="100%" cellspacing="0" cellpadding="0" '
                     'style="margin:8px 0;border-collapse:collapse">']
            parts.append("<tr>" + "".join(
                '<td style="%sbackground:#17171f;font-weight:700;">%s</td>'
                % (cell, _inline(c)) for c in header) + "</tr>")
            for row in rows:
                parts.append("<tr>" + "".join(
                    '<td style="%s">%s</td>' % (cell, _inline(c)) for c in row) + "</tr>")
            parts.append("</table>")
            out.append("".join(parts))
            continue

        # 分隔线
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flush_paragraph()
            close_lists()
            out.append('<hr style="border:none;border-top:1px solid #24242e;margin:12px 0;"/>')
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_paragraph()
            close_lists()
            level = len(m.group(1))
            size = {1: 19, 2: 17, 3: 15.5, 4: 14.5}.get(level, 14)
            out.append('<p style="margin:10px 0 4px 0;font-size:%gpx;font-weight:700;color:#f2f2f8;">%s</p>'
                       % (size, _inline(m.group(2))))
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            flush_paragraph()
            close_lists()
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            out.append('<table width="100%" cellpadding="6" cellspacing="0" style="margin:6px 0;">'
                       '<tr><td style="border-left:3px solid #4c4c66;color:#b9b9cc;">'
                       + "<br/>".join(_inline(x) for x in buf) +
                       '</td></tr></table>')
            continue

        # 列表
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if m:
            flush_paragraph()
            ordered = m.group(2)[0].isdigit()
            kind = "ol" if ordered else "ul"
            if not list_stack:
                out.append('<%s style="margin:4px 0 4px 18px;">' % kind)
                list_stack.append(kind)
            elif list_stack[-1] != kind:
                close_lists()
                out.append('<%s style="margin:4px 0 4px 18px;">' % kind)
                list_stack.append(kind)
            else:
                out.append("</li>")
            out.append('<li style="margin:2px 0;">%s' % _inline(m.group(3)))
            i += 1
            continue

        # 普通段落
        if list_stack:
            close_lists()
        paragraph.append(stripped)
        i += 1

    flush_paragraph()
    close_lists()
    return "".join(out)
