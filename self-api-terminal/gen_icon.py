#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 icon.ico：紫到洋红的圆角方块 + 终端提示符 “>_”。纯标准库。"""

import math
import os
import struct
import sys


def _seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    cx, cy = x1 + t * dx, y1 + t * dy
    return math.hypot(px - cx, py - cy)


def make_pixels(size):
    radius = size * 0.23
    c0 = (0x7C, 0x3A, 0xED)
    c1 = (0xC0, 0x26, 0xD3)
    th = size * 0.075
    ax1, ay1 = size * 0.29, size * 0.31
    ax2, ay2 = size * 0.46, size * 0.50
    ax3, ay3 = size * 0.29, size * 0.69
    ux1, uy1 = size * 0.55, size * 0.655
    ux2, uy2 = size * 0.72, size * 0.72

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            dx = max(radius - px, px - (size - radius), 0.0)
            dy = max(radius - py, py - (size - radius), 0.0)
            dist = math.hypot(dx, dy)
            cov = 1.0 if dist <= radius - 0.5 else (0.0 if dist >= radius + 0.5 else radius + 0.5 - dist)
            if cov <= 0:
                row.append((0, 0, 0, 0))
                continue
            t = (px + py) / (2.0 * max(size - 1, 1))
            r = int(c0[0] + (c1[0] - c0[0]) * t)
            g = int(c0[1] + (c1[1] - c0[1]) * t)
            b = int(c0[2] + (c1[2] - c0[2]) * t)

            d = min(_seg_dist(px, py, ax1, ay1, ax2, ay2),
                    _seg_dist(px, py, ax3, ay3, ax2, ay2))
            in_prompt = d < th / 2
            in_under = ux1 <= px <= ux2 and uy1 <= py <= uy2
            if in_prompt or in_under:
                r = g = b = 255
            row.append((r, g, b, int(255 * min(cov, 1.0))))
        rows.append(row)
    return rows


def dib(rows, size):
    out = bytearray()
    out += struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    for y in range(size - 1, -1, -1):
        for x in range(size):
            r, g, b, a = rows[y][x]
            out += bytes((b, g, r, a))
    row_bytes = ((size + 31) // 32) * 4
    out += b"\x00" * (row_bytes * size)
    return bytes(out)


def build_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    images = [(s, dib(make_pixels(s), s)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = body = b""
    for s, data in images:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        body += data
    with open(path, "wb") as f:
        f.write(header + entries + body)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "icon.ico")
    build_ico(target)
    print("wrote", target, os.path.getsize(target), "bytes")
