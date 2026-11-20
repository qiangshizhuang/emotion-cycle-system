# -*- coding: utf-8 -*-
"""
输出层：生成自包含 HTML 仪表盘（纯 SVG 手绘，不依赖任何 CDN）。
"""
import os
import math
import json
import pandas as pd
import numpy as np

import config

# ---------- 基础工具 ----------

def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


TEMP_STOPS = [(0, "#17324d"), (20, "#1f6f8b"), (40, "#3f9d8f"),
              (55, "#e0a33a"), (75, "#e2703a"), (100, "#d33b2c")]


def temp_color(v):
    v = max(0, min(100, v))
    for i in range(len(TEMP_STOPS) - 1):
        a, b = TEMP_STOPS[i], TEMP_STOPS[i + 1]
        if a[0] <= v <= b[0]:
            t = (v - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0
            ca = [int(a[1][i:i + 2], 16) for i in (1, 3, 5)]
            cb = [int(b[1][i:i + 2], 16) for i in (1, 3, 5)]
            rgb = [int(ca[j] + (cb[j] - ca[j]) * t) for j in range(3)]
            return "#%02x%02x%02x" % tuple(rgb)
    return TEMP_STOPS[-1][1]


def gauge_svg(score, color, size=260):
    """半圆温度计。"""
    cx, cy, r = size / 2, size * 0.66, size * 0.40
    def pt(angle_deg, radius=r):
        a = math.radians(angle_deg)
        return cx + radius * math.cos(a), cy - radius * math.sin(a)

    bands = [(0, 20, "#17324d"), (20, 40, "#1f6f8b"), (40, 55, "#3f9d8f"),
             (55, 75, "#e0a33a"), (75, 88, "#e2703a"), (88, 100, "#d33b2c")]
    parts = []
    for lo, hi, c in bands:
        a1 = 180 - lo * 1.8
        a2 = 180 - hi * 1.8
        x1, y1 = pt(a1); x2, y2 = pt(a2)
        parts.append(
            f'<path d="M {x1:.2f} {y1:.2f} A {r} {r} 0 0 1 {x2:.2f} {y2:.2f}" '
            f'fill="none" stroke="{c}" stroke-width="16" stroke-linecap="butt" opacity="0.92"/>'
        )
    ang = 180 - max(0, min(100, score)) * 1.8
    px, py = pt(ang, r * 0.46)
    nx, ny = pt(ang, r + 10)
    parts.append(f'<line x1="{px:.2f}" y1="{py:.2f}" x2="{nx:.2f}" y2="{ny:.2f}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="7" fill="{color}"/>')
    # 刻度
    for t in (0, 20, 40, 55, 75, 88, 100):
        a = 180 - t * 1.8
        x1, y1 = pt(a, r - 10); x2, y2 = pt(a, r - 18)
        parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#4a5568" stroke-width="1"/>')
    parts.append(f'<text x="{cx}" y="{cy - 12}" text-anchor="middle" font-size="40" font-weight="700" fill="{color}">{score:.0f}</text>')
    parts.append(f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" font-size="12" fill="#8b949e">情绪温度</text>')
    return f'<svg viewBox="0 0 {size} {size * 0.78:.0f}" width="100%" style="max-width:{size}px">{"".join(parts)}</svg>'


def line_chart(dates, series_list, phases=None, phase_colors=None,
               width=1200, height=320, ymin=0, ymax=100, y_label="", show_bands=True,
               bands_axis="left"):
    """折线图 + 阶段色带。series_list: [(values, color, name, width)]"""
    pad_l, pad_r, pad_t, pad_b = 44, 16, 16, 28
    W = width - pad_l - pad_r
    H = height - pad_t - pad_b
    n = len(dates)
    if n < 2:
        return ""
    xs = [pad_l + i * W / (n - 1) for i in range(n)]

    def ry(v):
        v = max(ymin, min(ymax, v))
        return pad_t + (ymax - v) / (ymax - ymin) * H

    parts = []
    # 阶段色带
    if show_bands and phases is not None:
        seg_start = 0
        for i in range(1, n + 1):
            if i == n or phases[i] != phases[seg_start]:
                c = phase_colors.get(phases[seg_start], "#000")
                x0 = xs[seg_start] - (W / (n - 1)) / 2 if seg_start > 0 else xs[0]
                x1 = xs[i - 1] + (W / (n - 1)) / 2 if i < n else xs[-1]
                parts.append(f'<rect x="{max(pad_l, x0):.1f}" y="{pad_t}" width="{max(1, x1 - max(pad_l, x0)):.1f}" height="{H}" fill="{c}" opacity="0.16"/>')
                seg_start = i

    # 网格
    for t in range(0, 5):
        v = ymin + (ymax - ymin) * t / 4
        y = ry(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + W}" y2="{y:.1f}" stroke="#21262d" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="#6e7681">{v:.0f}</text>')

    # 序列
    for vals, color, name, sw in series_list:
        pts = []
        for i, v in enumerate(vals):
            if pd.isna(v):
                continue
            pts.append((xs[i], ry(v)))
        if len(pts) < 2:
            continue
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>')

    # 面积（第一条）
    if series_list:
        vals, color, name, sw = series_list[0]
        pts = [(xs[i], ry(v)) for i, v in enumerate(vals) if not pd.isna(v)]
        if len(pts) >= 2:
            d = (f"M {pts[0][0]:.1f} {pad_t + H} L " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
                 + f" L {pts[-1][0]:.1f} {pad_t + H} Z")
            parts.append(f'<path d="{d}" fill="{color}" opacity="0.10"/>')

    # X 轴标签
    step = max(1, n // 8)
    for i in range(0, n, step):
        parts.append(f'<text x="{xs[i]:.1f}" y="{height - 8}" text-anchor="middle" font-size="10" fill="#6e7681">{dates[i][5:]}</text>')

    return f'<svg viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="none" style="display:block">{"".join(parts)}</svg>'


def bar_chart(dates, up_vals, dn_vals, width=560, height=230):
    """水滴图：0 轴居中，涨停向上（红），跌停向下（绿）。"""
    pad_l, pad_r, pad_t, pad_b = 46, 14, 16, 28
    W = width - pad_l - pad_r
    H = height - pad_t - pad_b
    n = len(dates)
    if n < 2:
        return ""
    mx_u = max(max(up_vals), 1)
    mx_d = max(max(dn_vals), 1)

    def y0():
        return pad_t + H * mx_u / (mx_u + mx_d)

    def ry(v):
        tot = mx_u + mx_d
        return pad_t + H * (mx_u - v) / tot

    bw = max(1.2, W / n * 0.66)
    parts = []
    zero = y0()
    # 网格
    for frac in (1.0, 0.5):
        for val, yy in ((mx_u * frac, ry(mx_u * frac)), (mx_d * frac, ry(-mx_d * frac))):
            parts.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{pad_l + W}" y2="{yy:.1f}" stroke="#1c232c"/>')
            parts.append(f'<text x="{pad_l - 7}" y="{yy + 3.5:.1f}" text-anchor="end" font-size="10" fill="#5c6673">{val:.0f}</text>')
    parts.append(f'<line x1="{pad_l}" y1="{zero:.1f}" x2="{pad_l + W}" y2="{zero:.1f}" stroke="#30363d"/>')
    parts.append(f'<text x="{pad_l - 7}" y="{zero + 3.5:.1f}" text-anchor="end" font-size="10" fill="#5c6673">0</text>')

    for i in range(n):
        x = pad_l + i * W / (n - 1) - bw / 2
        hu = up_vals[i] / (mx_u + mx_d) * H
        hd = dn_vals[i] / (mx_u + mx_d) * H
        if hu > 0.6:
            parts.append(f'<rect x="{x:.1f}" y="{zero - hu:.1f}" width="{bw:.1f}" height="{hu:.1f}" fill="#d94b3a" opacity="0.82"/>')
        if hd > 0.6:
            parts.append(f'<rect x="{x:.1f}" y="{zero:.1f}" width="{bw:.1f}" height="{hd:.1f}" fill="#2fa37f" opacity="0.82"/>')

    step = max(1, n // 8)
    for i in range(0, n, step):
        x = pad_l + i * W / (n - 1)
        parts.append(f'<text x="{x:.1f}" y="{height - 8}" text-anchor="middle" font-size="9.5" fill="#5c6673">{dates[i][2:]}</text>')
    return f'<svg viewBox="0 0 {width} {height}" width="100%" style="display:block">{"".join(parts)}</svg>'


def hbar(items, width=560):
    """横向得分条 items: [(label, value0_100, color)]"""
    rowh, gap = 34, 12
    h = len(items) * (rowh + gap)
    parts = []
    for i, (label, v, c) in enumerate(items):
        y = i * (rowh + gap) + 6
        parts.append(f'<text x="0" y="{y + 12}" font-size="12" fill="#8b949e">{_esc(label)}</text>')
        parts.append(f'<rect x="92" y="{y + 1}" width="{width - 92 - 46}" height="14" rx="7" fill="#21262d"/>')
        w = (width - 92 - 46) * max(0, min(100, v)) / 100
        parts.append(f'<rect x="92" y="{y + 1}" width="{w:.1f}" height="14" rx="7" fill="{c}"/>')
        parts.append(f'<text x="{width - 40}" y="{y + 12}" font-size="12" fill="#c9d1d9" font-weight="600">{v:.0f}</text>')
    return f'<svg viewBox="0 0 {width} {h}" width="100%" style="max-width:{width}px">{"".join(parts)}</svg>'
