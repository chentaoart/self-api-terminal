# -*- coding: utf-8 -*-
"""后台线程：聊天流 与 通用一次性任务。"""

from PySide6.QtCore import QThread, Signal

import api


class ChatThread(QThread):
    delta = Signal(str)
    reasoning = Signal(str)
    tool = Signal(str, str)
    toolResult = Signal(str, str)
    note = Signal(str)
    failed = Signal(str)

    def __init__(self, cfg: dict, messages: list, params=None, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self.messages = messages
        self.params = params or {}
        self.streamer = None

    def run(self):
        self.streamer = api.Streamer(self.cfg, self.messages, self._emit, self.params)
        try:
            self.streamer.run()
        except Exception as exc:
            self.failed.emit(str(exc))

    def _emit(self, event, *args):
        if event == "delta":
            self.delta.emit(args[0])
        elif event == "reasoning":
            self.reasoning.emit(args[0])
        elif event == "tool":
            self.tool.emit(args[0], args[1])
        elif event == "tool_result":
            self.toolResult.emit(args[0], args[1])
        elif event == "note":
            self.note.emit(args[0])

    def stop(self):
        if self.streamer is not None:
            self.streamer.cancel()


class Worker(QThread):
    ok = Signal(object)
    fail = Signal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self):
        try:
            self.ok.emit(self._fn(*self._args))
        except Exception as exc:
            self.fail.emit(str(exc))


# 短任务（比如探测上下文长度）用 run_bg：线程对象由模块持有，
# 关窗口时不会因为「QThread 在运行时被销毁」把进程带走。
_KEEP: list[Worker] = []


def run_bg(fn, *args, on_ok=None, on_fail=None):
    worker = Worker(fn, *args)

    def _cleanup():
        try:
            _KEEP.remove(worker)
        except ValueError:
            pass

    worker.finished.connect(_cleanup)
    if on_ok is not None:
        worker.ok.connect(on_ok)
    if on_fail is not None:
        worker.fail.connect(on_fail)
    _KEEP.append(worker)
    worker.start()
    return worker


def shutdown(ms: int = 1500):
    """退出前等一下还在跑的短任务，免得 QThread 在运行时被销毁。"""
    for worker in list(_KEEP):
        try:
            if worker.isRunning():
                worker.wait(ms)
        except Exception:
            pass
    _KEEP.clear()
    for thread in list(_RETIRING):
        try:
            if thread.isRunning():
                thread.wait(ms)
        except Exception:
            pass
    _RETIRING.clear()


# 已经收工、等回收的对话线程；留着引用，别让它在运行中被回收。
_RETIRING: list[QThread] = []


def retire(thread):
    """只把引用留着，不在这里删——删的动作必须回主线程做。"""
    if thread is None:
        return
    _RETIRING.append(thread)


def purge():
    """在主线程里回收确实跑完的线程。

    注意：不能在 QThread.finished 的回调里删自己——那个回调是在工作线程里跑的，
    删除 QThread 会把还在收尾的线程对象连根拔掉（表现为 0xc0000005）。
    """
    for thread in list(_RETIRING):
        try:
            if not thread.isRunning():
                _RETIRING.remove(thread)
                thread.deleteLater()
        except Exception:
            pass
