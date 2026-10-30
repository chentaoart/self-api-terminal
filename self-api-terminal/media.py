# -*- coding: utf-8 -*-
"""附件：图片存到数据目录，文本文件直接读进内存。

消息里只记元数据（图片存路径），JSON 不会因为贴了几张图就变成几 MB。
"""

import base64
import mimetypes
import secrets
from pathlib import Path

import store

IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_TEXT_BYTES = 200 * 1024


class AttachError(Exception):
    pass


def media_dir() -> Path:
    d = store.data_dir() / "media"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_image_name(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_MIME


def _text_attachment(name: str, raw: bytes) -> dict:
    if b"\x00" in raw[:4096]:
        raise AttachError("「%s」看起来是二进制文件，暂时只支持图片和文本" % name)
    truncated = len(raw) > MAX_TEXT_BYTES
    text = raw[:MAX_TEXT_BYTES].decode("utf-8", "replace")
    if truncated:
        text += "\n\n…（文件超过 %d KB，已截断）" % (MAX_TEXT_BYTES // 1024)
    return {
        "kind": "text",
        "name": name,
        "size": len(raw),
        "text": text,
        "truncated": truncated,
    }


def _image_attachment(name: str, raw: bytes) -> dict:
    if len(raw) > MAX_IMAGE_BYTES:
        raise AttachError("图片「%s」超过 %d MB" % (name, MAX_IMAGE_BYTES // (1024 * 1024)))
    ext = Path(name).suffix.lower()
    mime = IMAGE_MIME.get(ext) or mimetypes.guess_type(name)[0] or "image/png"
    target = media_dir() / (secrets.token_hex(8) + ext)
    target.write_bytes(raw)
    return {
        "kind": "image",
        "name": name,
        "size": len(raw),
        "mime": mime,
        "path": str(target),
    }


def add_path(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise AttachError("文件不存在：%s" % p)
    suffix = p.suffix.lower()
    if is_image_name(p.name):
        return _image_attachment(p.name, p.read_bytes())
    if suffix == ".pdf":
        return _pdf_attachment(p)
    if suffix in (".docx", ".doc"):
        return _docx_attachment(p)
    return _text_attachment(p.name, p.read_bytes())


def _text_result(name: str, text: str, size: int) -> dict:
    truncated = len(text) > MAX_TEXT_BYTES
    if truncated:
        text = text[:MAX_TEXT_BYTES] + "\n\n…（内容太长，已截断）"
    return {"kind": "text", "name": name, "size": size, "text": text, "truncated": truncated}


def _pdf_attachment(path: Path) -> dict:
    try:
        from pypdf import PdfReader
    except Exception:
        raise AttachError("读 PDF 需要 pypdf，先装一下：pip install pypdf")
    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
            if sum(len(x) for x in pages) > MAX_TEXT_BYTES:
                break
        text = "\n\n".join(x for x in pages if x.strip())
    except Exception as exc:
        raise AttachError("PDF 解析失败：%s" % exc)
    if not text.strip():
        raise AttachError("这个 PDF 里没有可提取的文字（可能是扫描件）")
    return _text_result(path.name, text, path.stat().st_size)


def _docx_attachment(path: Path) -> dict:
    if path.suffix.lower() == ".doc":
        raise AttachError("旧版 .doc 读不了，另存成 .docx 再发")
    try:
        import docx
    except Exception:
        raise AttachError("读 Word 需要 python-docx，先装一下：pip install python-docx")
    try:
        document = docx.Document(str(path))
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        text = "\n".join(parts)
    except Exception as exc:
        raise AttachError("Word 解析失败：%s" % exc)
    if not text.strip():
        raise AttachError("这个文档里没有可提取的文字")
    return _text_result(path.name, text, path.stat().st_size)


def add_image_bytes(raw: bytes, name: str = "粘贴的图片.png") -> dict:
    return _image_attachment(name, raw)


def data_url(att: dict) -> str:
    p = Path(att.get("path") or "")
    if not p.is_file():
        raise AttachError("图片文件已丢失：%s" % (att.get("name") or p.name))
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    mime = att.get("mime") or "image/png"
    return "data:%s;base64,%s" % (mime, b64)


def summarize(att: dict) -> str:
    name = att.get("name") or "附件"
    size = att.get("size") or 0
    if size < 1024:
        human = "%d B" % size
    elif size < 1024 * 1024:
        human = "%.1f KB" % (size / 1024)
    else:
        human = "%.1f MB" % (size / (1024 * 1024))
    return "%s · %s" % (name, human)
