# -*- coding: utf-8 -*-
"""语音输入：借 Windows 自带的听写引擎（System.Speech）。

要求：有麦克风，并且装了对应语言的「语音识别」组件。
中文识别包不是默认安装的，没装就只能识别英文或直接报错。
"""

import subprocess

CREATE_NO_WINDOW = 0x08000000

_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
try {
  $rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine
  $rec.SetInputToDefaultAudioDevice()
  $rec.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
  $rec.InitialSilenceTimeout = [TimeSpan]::FromSeconds(4)
  $rec.BabbleTimeout = [TimeSpan]::FromSeconds(2)
  $r = $rec.Recognize([TimeSpan]::FromSeconds(%d))
  if ($r) {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    Write-Output $r.Text
  }
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 2
} finally {
  if ($rec) { $rec.Dispose() }
}
"""


class VoiceError(Exception):
    pass


def listen(seconds: int = 8) -> str:
    """听一句话，返回识别到的文字；失败抛 VoiceError。"""
    script = _PS % seconds
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=seconds + 15, creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError:
        raise VoiceError("找不到 powershell，语音输入用不了")
    except subprocess.TimeoutExpired:
        raise VoiceError("等了太久没听到声音")
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        msg = detail[-1] if detail else "未知错误"
        if "没有" in msg or "not" in msg.lower():
            raise VoiceError("系统里没有可用的语音识别引擎：%s" % msg)
        raise VoiceError("语音识别失败：%s" % msg)
    text = (proc.stdout or "").strip()
    if not text:
        raise VoiceError("没听清（也可能是麦克风没权限）")
    return text
