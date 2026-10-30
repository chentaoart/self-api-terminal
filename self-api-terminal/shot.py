# -*- coding: utf-8 -*-
"""抓一张窗口截图（把窗口临时置顶再抓，避免被别的窗口挡住）。

    .venv\\Scripts\\python.exe shot.py out.png
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

from PySide6.QtWidgets import QApplication

user32 = ctypes.windll.user32

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010

TITLE_PART = "自用 API 终端"


def find_window():
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def enum(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if TITLE_PART in buf.value:
            found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(enum, 0)
    return found[0] if found else (None, None)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "shot.png"
    hwnd, title = find_window()
    if not hwnd:
        print("没找到窗口（标题里应包含 %r）" % TITLE_PART)
        return 1
    print("窗口:", hwnd, title)

    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE)
    user32.SetForegroundWindow(hwnd)
    app = QApplication([])
    time.sleep(1.2)
    app.processEvents()

    screen = app.primaryScreen()
    pix = screen.grabWindow(hwnd)
    pix.save(out)
    print("saved", out, pix.width(), "x", pix.height())

    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
