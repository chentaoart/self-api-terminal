# -*- coding: utf-8 -*-
"""把 PyInstaller 的 ASCII 文件名/目录名改成中文（PowerShell 传中文会乱码，所以放这里）。"""
import pathlib
import sys

dist = pathlib.Path(__file__).resolve().parent / "dist"
CN = "自用API终端"

single = dist / "HermesTerminalNative.exe"
folder = dist / "HermesTerminalNative"

if folder.is_dir():
    target_dir = dist / CN
    if target_dir.exists():
        for p in sorted(target_dir.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        target_dir.rmdir()
    exe = folder / "HermesTerminalNative.exe"
    if exe.exists():
        exe.rename(folder / (CN + ".exe"))
    folder.rename(target_dir)
    print(target_dir / (CN + ".exe"))
elif single.exists():
    target = dist / (CN + ".exe")
    if target.exists():
        target.unlink()
    single.rename(target)
    print(target)
else:
    print("没找到打包产物")
    sys.exit(1)
