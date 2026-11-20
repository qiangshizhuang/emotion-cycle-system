# -*- coding: utf-8 -*-
"""组合图：上=股价走势，下=情绪温度，背景=阶段色带"""
import pandas as pd


def combined_chart(dates, idx_vals, temp_vals, ma5_vals, phases, phase_colors,
                   width=1200, height=430, idx_label="等权指数", idx_color="#5b9bd5"):
    pad_l, pad_r = 58, 14
    n = len(dates)
    if n < 2:
        return ""
    W = width - pad_l - pad_r
    # 上方面板（指数）
    t_top, t_h = 18, 190
    # 下方面板（温度）
    b_top, b_h = 262, 132
    bottom = b_top + b_h

    xs = [pad_l + i * W / (n - 1) for i in range(n)]
    step_w = W / (n - 1)

    lo, hi = min(idx_vals), max(idx_vals)
    pad_ = (hi - lo) * 0.08 or 1
    ilo, ihi = lo - pad_, hi + pad_

    def ry_idx(v):
        return t_top + (ihi - v) / (ihi - ilo) * t_h

    def ry_t(v):
        v = max(0, min(100, v))
        return b_top + (100 - v) / 100 * b_h

    p = []
    # ---- 阶段色带（贯通两个面板）----
    seg_start = 0
    for i in range(1, n + 1):
        if i == n or phases[i] != phases[seg_start]:
            c = phase_colors.get(phases[seg_start], "#000")
            x0 = xs[seg_start] - step_w / 2 if seg_start > 0 else xs[0]
            x1 = xs[i - 1] + step_w / 2 if i < n else xs[-1]
            x0 = max(pad_l, x0)
            p.append(f'<rect x="{x0:.1f}" y="{t_top}" width="{max(1.0, x1 - x0):.1f}" height="{bottom - t_top}" fill="{c}" opacity="0.15"/>')
            seg_start = i

    # ---- 上方面板网格 ----
    for k in range(4):
        v = ilo + (ihi - ilo) * k / 3
        y = ry_idx(v)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + W}" y2="{y:.1f}" stroke="#1c232c" stroke-width="1"/>')
        p.append(f'<text x="{pad_l - 7}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10" fill="#5c6673">{v:,.0f}</text>')

    # 指数折线 + 面积
    pts = [(xs[i], ry_idx(idx_vals[i])) for i in range(n)]
    d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    area = f"M {pts[0][0]:.1f} {t_top + t_h} L " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts) + f" L {pts[-1][0]:.1f} {t_top + t_h} Z"
    p.append(f'<path d="{area}" fill="{idx_color}" opacity="0.13"/>')
    p.append(f'<path d="{d}" fill="none" stroke="{idx_color}" stroke-width="1.9" stroke-linejoin="round"/>')

    # 指数高低点标注
    i_max = idx_vals.index(max(idx_vals)); i_min = idx_vals.index(min(idx_vals))
    for ii, tag in ((i_max, "高"), (i_min, "低")):
        p.append(f'<circle cx="{xs[ii]:.1f}" cy="{ry_idx(idx_vals[ii]):.1f}" r="2.6" fill="{idx_color}"/>')
        p.append(f'<text x="{xs[ii]:.1f}" y="{ry_idx(idx_vals[ii]) + (-8 if tag == "高" else 14):.1f}" text-anchor="middle" font-size="9.5" fill="#7d8694">{tag}</text>')

    p.append(f'<text x="{pad_l}" y="{t_top - 5}" font-size="11" fill="#7d8694">{idx_label}</text>')

    # ---- 阶段事件标记：高潮 ▲ / 冰点 ● ----
    ev = []
    for i in range(1, n):
        if phases[i] == phases[i - 1]:
            continue
        if phases[i] in ("CLIMAX", "FREEZE"):
            ev.append((i, phases[i]))
    # 标签防重叠：同类标签间隔 < 12 个点则跳过
    last_idx = {"CLIMAX": -99, "FREEZE": -99}
    for i, ph in ev:
        if i - last_idx[ph] < 12:
            continue
        last_idx[ph] = i
        x = xs[i]
        if ph == "CLIMAX":
            y = t_top + 12
            p.append(f'<path d="M {x:.1f} {y - 7} L {x - 4.5:.1f} {y + 1} L {x + 4.5:.1f} {y + 1} Z" fill="#d33b2c" opacity="0.9"/>')
        else:
            y = t_top + t_h - 10
            p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="#1f6f8b" opacity="0.9"/>')
            p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="#0b0e14"/>')

    # ---- 分隔 ----
    p.append(f'<line x1="{pad_l}" y1="{b_top - 26}" x2="{pad_l + W}" y2="{b_top - 26}" stroke="#21262d" stroke-dasharray="3 3"/>')
    p.append(f'<text x="{pad_l}" y="{b_top - 10}" font-size="11" fill="#7d8694">情绪温度（0-100）</text>')

    # ---- 下方面板网格 ----
    for v in (0, 25, 50, 75, 100):
        y = ry_t(v)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + W}" y2="{y:.1f}" stroke="#1c232c"/>')
        p.append(f'<text x="{pad_l - 7}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10" fill="#5c6673">{v}</text>')
    # 关键分界线
    for v, lbl in ((80, "高潮线 80"), (20, "冰点线 20")):
        y = ry_t(v)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + W}" y2="{y:.1f}" stroke="#3a4550" stroke-dasharray="4 3" stroke-width="1"/>')
        p.append(f'<text x="{pad_l + W - 2}" y="{y - 4:.1f}" text-anchor="end" font-size="9" fill="#4c5663">{lbl}</text>')

    # 温度面积 + 线
    tpts = [(xs[i], ry_t(temp_vals[i])) for i in range(n) if not pd.isna(temp_vals[i])]
    if len(tpts) > 1:
        tarea = (f"M {tpts[0][0]:.1f} {b_top + b_h} L "
                 + " L ".join(f"{x:.1f} {y:.1f}" for x, y in tpts)
                 + f" L {tpts[-1][0]:.1f} {b_top + b_h} Z")
        p.append(f'<path d="{tarea}" fill="#e2703a" opacity="0.16"/>')
        p.append('<path d="M ' + " L ".join(f"{x:.1f} {y:.1f}" for x, y in tpts) + '" fill="none" stroke="#e2703a" stroke-width="1.8"/>')
    # 5 日均
    mpts = [(xs[i], ry_t(ma5_vals[i])) for i in range(n) if not pd.isna(ma5_vals[i])]
    if len(mpts) > 1:
        p.append('<path d="M ' + " L ".join(f"{x:.1f} {y:.1f}" for x, y in mpts) + '" fill="none" stroke="#9aa4b2" stroke-width="1" stroke-dasharray="3 2" opacity="0.8"/>')

    # ---- X 轴 ----
    step = max(1, n // 9)
    for i in range(0, n, step):
        p.append(f'<text x="{xs[i]:.1f}" y="{bottom + 16}" text-anchor="middle" font-size="9.5" fill="#5c6673">{dates[i][2:]}</text>')

    return f'<svg viewBox="0 0 {width} {bottom + 24}" width="100%" preserveAspectRatio="none" style="display:block">{"".join(p)}</svg>'
