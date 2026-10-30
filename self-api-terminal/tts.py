# -*- coding: utf-8 -*-
"""朗读：用 Windows 自带的 SAPI 语音。"""

import re

from PySide6.QtCore import QLocale


def _clean(text: str) -> str:
    """把 Markdown 洗成适合朗读的纯文本。"""
    s = text or ""
    s = re.sub(r"```[\s\S]*?```", "（代码块）", s)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"[*_~]{1,3}", "", s)
    s = re.sub(r"^\s*>\s?", "", s, flags=re.M)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


class Tts:
    def __init__(self):
        self.engine = None
        self.voices = []
        self.error = ""
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            self.engine = QTextToSpeech("sapi")
            self.voices = list(self.engine.availableVoices())
        except Exception as exc:
            self.error = str(exc)
            return

        if not self.voices:
            self.error = ("系统里没有可用的朗读语音。\n"
                          "可以在「设置 → 时间和语言 → 语音」里装一个中文语音包。")
            return
        zh = [v for v in self.voices if v.locale().language() == QLocale.Chinese]
        try:
            self.engine.setVoice((zh or self.voices)[0])
        except Exception:
            pass

    @property
    def ready(self) -> bool:
        return self.engine is not None and bool(self.voices)

    def speak(self, text: str):
        if not self.ready:
            return False
        clean = _clean(text)
        if not clean:
            return False
        self.engine.stop()
        self.engine.say(clean)
        return True

    def stop(self):
        if self.engine is not None:
            self.engine.stop()

    def set_rate(self, value: float):
        if self.engine is not None:
            self.engine.setRate(value)
