# -*- coding: utf-8 -*-
"""HTML 仪表盘生成"""
import os
import time
import pandas as pd
import numpy as np

import config
from output import charts
from output import combo_chart as combo


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b0e14;color:#c9d1d9;font-family:-apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
     font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1280px;margin:0 auto;padding:28px 20px 60px}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}
header{display:flex;justify-content:space-between;align-items:flex-end;padding-bottom:16px;
       border-bottom:1px solid #21262d;margin-bottom:22px;flex-wrap:wrap;gap:10px}
h1{font-size:20px;font-weight:600;letter-spacing:.5px;color:#e6edf3}
h1 span{color:#6e7681;font-weight:400;font-size:13px;margin-left:10px}
.meta{font-size:12px;color:#6e7681;text-align:right}
section{margin-bottom:26px}
.card{background:#11161f;border:1px solid #21262d;border-radius:10px;padding:18px 20px}
.card h2{font-size:13px;font-weight:600;color:#8b949e;letter-spacing:1px;margin-bottom:14px;
         text-transform:uppercase;display:flex;align-items:center;gap:8px}
.card h2:before{content:"";width:3px;height:13px;background:#30363d;border-radius:2px}
.hero{display:grid;grid-template-columns:260px 1fr 340px;gap:18px;align-items:stretch}
@media(max-width:980px){.hero{grid-template-columns:1fr}}
.phase-badge{display:inline-flex;align-items:center;gap:10px;padding:6px 14px;border-radius:999px;
             font-size:13px;font-weight:600;margin-bottom:12px}
.phase-name{font-size:46px;font-weight:700;line-height:1.1;letter-spacing:2px}
.phase-sub{color:#8b949e;font-size:13px;margin-top:8px}
.desc{color:#c9d1d9;font-size:14px;margin-top:14px;padding-top:14px;border-top:1px dashed #21262d;line-height:1.75}
.kv{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #1a2029;font-size:13px}
.kv:last-child{border:none}
.kv b{font-weight:600}
.kv .k{color:#8b949e}
.advice-do{color:#3fb950}
.advice-avoid{color:#f85149}
.tip{background:#1a2029;border-left:2px solid #30363d;padding:10px 12px;border-radius:0 6px 6px 0;
     font-size:12.5px;color:#9aa4b2;margin-top:12px;line-height:1.7}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:980px){.grid4{grid-template-columns:repeat(2,1fr)}.grid3{grid-template-columns:1fr}.grid2{grid-template-columns:1fr}}
.kpi{background:#0e131b;border:1px solid #21262d;border-radius:8px;padding:12px 14px}
.kpi .label{font-size:11.5px;color:#6e7681;margin-bottom:6px;letter-spacing:.3px}
.kpi .val{font-size:24px;font-weight:700;line-height:1.1}
.kpi .sub{font-size:11px;color:#6e7681;margin-top:6px}
.up{color:#f0544c}.down{color:#2ea88a}.neutral{color:#c9d1d9}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:right;color:#6e7681;font-weight:500;padding:8px 6px;border-bottom:1px solid #21262d;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td{text-align:right;padding:8px 6px;border-bottom:1px solid #161b22;white-space:nowrap}
tbody tr:hover{background:#161b22}
.legend{display:flex;gap:16px;font-size:12px;color:#8b949e;margin-top:12px;flex-wrap:wrap;align-items:center}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:middle}
.strip{display:flex;gap:2px;margin-top:6px;flex-wrap:wrap}
.chip{width:14px;height:26px;border-radius:2px;position:relative}
.chip:hover{outline:1px solid #c9d1d9}
footer{color:#484f58;font-size:11.5px;border-top:1px solid #21262d;padding-top:16px;line-height:1.9}
footer b{color:#6e7681}
.tag{font-size:11px;padding:2px 7px;border-radius:4px;background:#21262d;color:#8b949e;margin-left:6px}
.tier{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}
@media(max-width:980px){.tier{grid-template-columns:repeat(2,1fr)}}
.seg{background:#0d1219;border:1px solid #21262d;border-radius:8px;padding:13px 14px;opacity:.45;
     transition:.18s;position:relative}
.seg .rng{font-size:11.5px;color:#8b949e;letter-spacing:.3px}
.seg .act{font-size:19px;font-weight:700;margin:5px 0 3px;line-height:1.15}
.seg .why{font-size:11px;color:#6e7681;line-height:1.5}
.seg.on{opacity:1;box-shadow:0 0 0 1px currentColor inset;background:#131b25}
.stale{background:#2a1c1c;border:1px solid #7a3030;color:#ffb3a7;border-radius:8px;
       padding:11px 14px;font-size:12.5px;margin-bottom:18px;line-height:1.7}
.stale b{color:#ff7a6a}
.fresh{font-size:11.5px;color:#3fb950}
"""


def _fmt(v, nd=0, suffix=""):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:,.{nd}f}{suffix}"


def _chg_html(v, nd=0, suffix="", reverse=False):
    if v is None or pd.isna(v):
        return '<span class="neutral">—</span>'
    cls = "up" if v > 0 else ("down" if v < 0 else "neutral")
    if reverse:
        cls = {"up": "down", "down": "up", "neutral": "neutral"}[cls]
    sign = "+" if v > 0 else ""
    return f'<span class="{cls}">{sign}{v:,.{nd}f}{suffix}</span>'


def describe(phase, r):
    """自动生成一句话定性。"""
    zt, dt, mb = int(r["zt_count"]), int(r["dt_count"]), int(r["max_board"])
    prem = r["prem"] if pd.notna(r["prem"]) else 0
    seal = r["seal_rate"] * 100 if pd.notna(r["seal_rate"]) else 0
    bl = int(r["big_loss"])
    amt = r["amount_yi"] if pd.notna(r["amount_yi"]) else 0
    if phase == "FREEZE":
        return (f"涨停仅 <b>{zt}</b> 家而跌停 <b>{dt}</b> 家，大面 <b>{bl}</b> 只，连板高度压到 <b>{mb}</b> 板，"
                f"两市成交 <b>{amt:,.0f}</b> 亿。资金无处可去，接力资金连续亏钱——这是典型的冰点特征。")
    if phase == "REPAIR":
        return (f"涨停回升到 <b>{zt}</b> 家，跌停收敛至 <b>{dt}</b> 家，昨涨停今日平均 <b>{prem:+.1f}%</b>。"
                f"亏钱效应开始减弱，但封板率仅 <b>{seal:.0f}%</b>，高度 <b>{mb}</b> 板——修复期，赔率好转但胜率未确认。")
    if phase == "FERMENT":
        return (f"涨停 <b>{zt}</b> 家、连板高度 <b>{mb}</b> 板、封板率 <b>{seal:.0f}%</b>，"
                f"昨涨停今日仍溢价 <b>{prem:+.1f}%</b>。赚钱效应扩散，主线明确，这是主升阶段。")
    if phase == "CLIMAX":
        return (f"涨停爆量至 <b>{zt}</b> 家，昨涨停今日溢价 <b>{prem:+.1f}%</b>，高度打开到 <b>{mb}</b> 板，"
                f"成交 <b>{amt:,.0f}</b> 亿。情绪最亢奋的一天，也是兑现窗口——高潮之后必然分歧。")
    if phase == "DIVERGE":
        return (f"涨停缩至 <b>{zt}</b> 家，昨涨停今日转为 <b>{prem:+.1f}%</b>，封板率 <b>{seal:.0f}%</b>，"
                f"炸板 <b>{int(r['zb_count'])}</b> 只。高位股开始出现分歧，接力资金开始亏钱，进入防守。")
    return (f"跌停 <b>{dt}</b> 家、大面 <b>{bl}</b> 只，昨涨停今日 <b>{prem:+.1f}%</b>，涨停萎缩到 <b>{zt}</b> 家。"
            f"退潮期的典型形态：赚钱效应消失，亏钱效应放大。")


def build_html(sent, stats, out_path, trans=None):
    d = sent[sent["phase_valid"]].copy().reset_index(drop=True)
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else last
    ph = last["phase"]
    pname = config.PHASES[ph]["name"]
    pcol = config.PHASES[ph]["color"]
    adv = config.ADVICE[ph]
    T = last["score"]

    view = d.tail(config.REPORT_DAYS).reset_index(drop=True)

    # ---- 仪表盘 + 阶段卡 ----
    gauge = charts.gauge_svg(T, charts.temp_color(T) if hasattr(charts, "temp_color") else pcol)

    tempidx = d.tail(config.REPORT_DAYS - 8).index.max() if len(d) > 8 else 0
    hist_view = d.iloc[-config.CHART_DAYS:].reset_index(drop=True)
    phase_n = int(last["phase_day_n"])
    phase_len = int(last["phase_len"])

    # 关键指标
    kpis = [
        ("涨停家数", f"{int(last['zt_count'])}", f"前值 {int(prev['zt_count'])}　分位 {last['zt_pct']:.0f}%", "#f0544c"),
        ("跌停家数", f"{int(last['dt_count'])}", f"门槛 60 / 150 / 400", "#2ea88a"),
        ("最高连板", f"{int(last['max_board'])} 板", f"连板股 {int(last['board2'])} 只", "#e8a33d"),
        ("封板率", f"{last['seal_rate']*100:.0f}%" if pd.notna(last['seal_rate']) else "—",
         f"炸板 {int(last['zb_count'])} 只", "#c9d1d9"),
        ("昨涨停溢价", f"{last['prem']:+.2f}%" if pd.notna(last['prem']) else "—",
         f"红盘率 {last['prem_win']:.0f}%" if pd.notna(last['prem_win']) else "", "#f0544c" if (pd.notna(last['prem']) and last['prem'] > 0) else "#2ea88a"),
        ("大面数", f"{int(last['big_loss'])}", f"辅助门槛 400", "#2ea88a"),
        ("两市成交", f"{last['amount_yi']:,.0f} 亿", f"20日均量比 {last['amt_ratio']:.2f}", "#c9d1d9"),
        ("上证指数", f"{last['idx_close']:,.0f}" if pd.notna(last.get('idx_close', np.nan)) else "—",
         f"当日 {last['idx_pct']:+.2f}%" if pd.notna(last['idx_pct']) else "", "#f0544c" if (pd.notna(last['idx_pct']) and last['idx_pct'] > 0) else "#2ea88a"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="label">{k}</div><div class="val num" style="color:{c}">{v}</div>'
        f'<div class="sub num">{s}</div></div>' for k, v, s, c in kpis
    )

    # ---- 跌停家数分级：这是判断「冰点能不能买」的唯一刻度 ----
    dt_n, bl_n = int(last["dt_count"]), int(last["big_loss"])
    TIERS = [
        ("0 ~ 59 家", "0~1 成", "没触发，空仓等", "#3a4759", 0),
        ("60 ~ 149 家", "2~3 成", "20 次 · T+20 +6.86% · 胜率 75%", "#3fb950", 60),
        ("150 ~ 399 家", "5~6 成", "8 次 · T+20 +13.32% · 8 次全赚", "#e8a33d", 150),
        ("≥ 400 家", "8 成", "4 次 · T+20 +15.04% · 最差 +8.1%", "#f0544c", 400),
    ]

    def _tier_of(dtv, blv):
        if dtv >= 400:
            return 3
        if dtv >= 150:
            return 2
        if dtv >= 60 or blv >= 400:
            return 1          # 大面 400 家 ≈ 一级的量级，仓位同样是 2 成
        return 0

    cur = _tier_of(dt_n, bl_n)

    # 崩盘后的建仓窗口：恐慌当天没买，不等于第二天就不该有仓位。
    # 跌停潮次日家数立刻消失，只看当天会把「已经建好的仓」判成空仓，来回打脸。
    LOOKBACK = 10
    last_hit = None
    for _, r0 in d.tail(LOOKBACK).iloc[::-1].iterrows():
        t0 = _tier_of(int(r0["dt_count"]), int(r0["big_loss"]))
        if t0 > 0:
            last_hit = (str(r0["date"]), t0, int(r0["dt_count"]), int(r0["big_loss"]))
            break
    win_tier = last_hit[1] if last_hit else 0
    show_tier = cur if cur > 0 else win_tier
    hit_days = 0
    if show_tier > 0:
        hit_days = len(d) - 1 - d.index[d["date"] == last_hit[0]][0] if last_hit else 0

    tier_html = ""
    for i, (rng, act, why, col, _) in enumerate(TIERS):
        on = (i == show_tier and show_tier > 0)
        badge = ""
        if on:
            badge = ('<span style="position:absolute;top:-9px;right:10px;font-size:10px;font-weight:700;'
                     f'background:{col};color:#0b0e14;padding:1px 6px;border-radius:3px;letter-spacing:.4px">'
                     f'{"今天" if cur > 0 else f"{-hit_days}日前"}</span>')
        tier_html += (f'<div class="seg{" on" if on else ""}" style="color:{col};position:relative">'
                      f'{badge}<div class="rng">{rng}</div><div class="act">{act}</div>'
                      f'<div class="why">{why}</div></div>')

    if cur == 3:
        gap_txt = "已在最高档，历史仅 4 次"
    elif cur > 0:
        gap_txt = f"再增 <b>{TIERS[cur + 1][4] - dt_n}</b> 家跌停进下一档"
    elif win_tier > 0:
        gap_txt = f"恐慌已过去 {hit_days} 个交易日"
    else:
        gap_txt = "近 10 日没有触发"

    if cur == 3:
        verdict = (f'<b style="color:#f0544c">三级触发</b>：跌停 {dt_n} 家，千股跌停，打到 <b>8 成</b>。'
                   f'留 2 成现金，持有 20 个交易日，不要做短线。')
    elif cur == 2:
        verdict = (f'<b style="color:#e8a33d">二级触发</b>：跌停 {dt_n} 家，全系统赔率最好的位置，'
                   f'加到 <b>5~6 成</b>。历史 8 次，20 个交易日后全部为正。')
    elif cur == 1:
        verdict = (f'<b style="color:#3fb950">一级触发</b>：跌停 {dt_n} 家 / 大面 {bl_n} 家，建底仓 <b>2~3 成</b>。'
                   f'别一次打满，{gap_txt}就加到 5~6 成。')
    elif win_tier > 0:
        verdict = (f'<b style="color:#3fb950">建仓窗口内（{hit_days} 个交易日前的恐慌已触发）</b>：'
                   f'今天跌停只剩 <b>{dt_n}</b> 家、大面 <b>{bl_n}</b> 家，恐慌退去，但仓位<b>不是清零而是维持</b>——'
                   f'上一档给的是 {TIERS[win_tier][1]}，现在<b>持有不动</b>，不加也不减。<br>'
                   f'加仓要等两件事之一：① 跌停重新回到 {TIERS[win_tier][4]} 家以上（二次探底，那是更好的机会）；'
                   f'② 涨停站上 80 家、封板率回到 65% 以上、溢价连续 3 日为正（修复确认，按趋势仓位做）。'
                   f'10 个交易日后仍无其一，仓位退回 1~2 成。')
    else:
        verdict = (f'<b>全场空仓等待</b>：跌停 {dt_n} 家、大面 {bl_n} 家都没到门槛，近 10 日也没触发过。'
                   f'这个状态后 20 日平均只 +0.4%，不值得赌。')


    # 数据新鲜度
    today = time.strftime("%Y-%m-%d")
    hm = time.strftime("%H:%M")
    last_day = str(last["date"])
    gap_nat = (pd.Timestamp(today) - pd.Timestamp(last_day)).days
    if last_day == today:
        fresh_html = '<span class="fresh">● 已更新至今日收盘</span>'
        stale_html = ""
    elif pd.Timestamp(today).weekday() < 5 and hm >= "15:10" and gap_nat <= 3:
        fresh_html = f'<span style="color:#ff7a6a">● 数据不是今天的</span>'
        stale_html = (f'<div class="stale">⚠ 今天是 <b>{today}</b>（{hm}，已收盘），但报告的最新数据是 '
                      f'<b>{last_day}</b>，落后 <b>{gap_nat}</b> 天。<br>'
                      f'说明这次补数据没成功（网络被卡、或接口限流）。'
                      f'<b>不要用这份报告做决策</b>——关掉重开一次，窗口里会打印补数据的进度和失败原因。</div>')
    else:
        fresh_html = f'<span style="color:#e8b04b">● 最新 {last_day}（今日未收盘或休市）</span>'
        stale_html = ""

    # 分项
    items = [
        ("涨停强度 20%", last["s_limit_up"], "#e2703a"),
        ("封板质量 15%", last["s_seal_quality"], "#e0a33a"),
        ("赚钱效应 25%", last["s_money_effect"], "#d33b2c"),
        ("亏钱效应 20%", last["s_loss_effect"], "#3f9d8f"),
        ("市场广度 10%", last["s_breadth"], "#1f6f8b"),
        ("量能 10%", last["s_volume"], "#5b7fa6"),
    ]
    bars = charts.hbar(items)

    # 主图：等权指数 + 情绪温度 + 阶段色带
    temp_svg = combo.combined_chart(
        hist_view["date"].tolist(),
        hist_view["eq_index"].ffill().bfill().tolist(),
        hist_view["score"].tolist(),
        hist_view["score_ma5"].tolist(),
        hist_view["phase"].tolist(),
        {k: v["color"] for k, v in config.PHASES.items()},
        idx_label="全市场等权指数（剔除ST/次新，基点1000）",
    )

    # 涨跌停柱状
    ztdt_svg = charts.bar_chart(hist_view["date"].tolist(),
                                hist_view["zt_count"].tolist(),
                                hist_view["dt_count"].tolist())

    # 阶段画像表
    st_rows = ""
    for _, r in stats.iterrows():
        c = config.PHASES[r["code"]]["color"]
        st_rows += (
            f'<tr><td><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:{c};margin-right:7px"></span>{r["阶段"]}</td>'
            f'<td>{int(r["天数"])}</td><td>{r["占比%"]:.1f}%</td><td>{int(r["出现次数"])}</td>'
            f'<td>{r["平均持续"]:.1f}</td><td>{int(r["最长持续"])}</td><td>{r["平均温度"]:.1f}</td>'
            f'<td>{_chg_html(r["次日指数均值%"], 2, "%")}</td>'
            f'<td>{r["次日涨停均值"]:.0f}</td>'
            f'<td>{_chg_html(r["次日溢价均值%"], 2, "%")}</td>'
            f'<td>{_chg_html(r["次日温度变化"], 1)}</td></tr>'
        )

    # 历史同类阶段
    same = d[(d["phase"] == ph) & (d["phase_day_n"] == 1)].tail(6)
    hist_rows = ""
    for _, r in same.iloc[::-1].iterrows():
        idx0 = d.index[d["date"] == r["date"]]
        if len(idx0) == 0:
            continue
        i0 = idx0[0]
        end_i = min(i0 + int(r["phase_len"]) - 1, len(d) - 1)
        fwd_i = min(end_i + 5, len(d) - 1)
        fwd = (d.loc[fwd_i, "eq_index"] / d.loc[end_i, "eq_index"] - 1) * 100 if pd.notna(d.loc[end_i, "eq_index"]) else np.nan
        hist_rows += (
            f'<tr><td>{r["date"]}</td><td>{int(r["phase_len"])} 日</td>'
            f'<td>{d.loc[end_i, "date"]}</td>'
            f'<td class="num">{d.loc[end_i, "score"]:.0f}</td>'
            f'<td>{_chg_html(fwd, 2, "%")}</td></tr>'
        )
    if not hist_rows:
        hist_rows = '<tr><td colspan="5" style="text-align:center;color:#484f58">样本不足</td></tr>'

    # ---- 次日去向概率条 ----
    next_bar = ""
    if trans is not None and ph in trans.index:
        row = trans.loc[ph].sort_values(ascending=False)
        row = row[row > 0]
        segs = ""
        for k, v in row.items():
            c = config.PHASES[k]["color"]
            txt = f'{config.PHASES[k]["name"]} {v:.0f}%' if v >= 9 else f'{v:.0f}%'
            segs += (f'<div style="flex:{v};min-width:{52 if v < 9 else 0}px;background:{c};height:34px;'
                     f'display:flex;align-items:center;justify-content:center;font-size:11.5px;color:#fff;'
                     f'font-weight:600;overflow:hidden;white-space:nowrap" '
                     f'title="{config.PHASES[k]["name"]} {v:.1f}%">{txt}</div>')
        cnt = int((d["phase"] == ph).sum())
        next_bar = (f'<div class="card" style="padding:14px 20px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:9px">'
                    f'<span style="font-size:13px;color:#8b949e">次日去向概率 · 基于历史上处于「{pname}」的 {cnt} 个交易日</span>'
                    f'<span style="font-size:11.5px;color:#5c6673">这是一个马尔可夫转移矩阵，不是预测</span></div>'
                    f'<div style="display:flex;gap:2px;border-radius:6px;overflow:hidden">{segs}</div></div>')

    # 近 60 日阶段序列
    strip = ""
    for _, r in d.tail(60).iterrows():
        c = config.PHASES[r["phase"]]["color"]
        strip += f'<div class="chip" style="background:{c}" title="{r["date"]} {r["phase_name"]} 温度{r["score"]:.0f}"></div>'

    # 图例
    legend = "".join(f'<span><i style="background:{v["color"]}"></i>{v["name"]}</span>'
                     for k, v in config.PHASES.items())

    # 明细表（最近 40 日）
    det_rows = ""
    for _, r in d.tail(40).iloc[::-1].iterrows():
        c = config.PHASES[r["phase"]]["color"]
        det_rows += (
            f'<tr><td>{r["date"]}</td>'
            f'<td style="text-align:left"><span style="color:{c};font-weight:600">{r["phase_name"]}</span></td>'
            f'<td class="num">{r["score"]:.0f}</td>'
            f'<td class="num">{int(r["zt_count"])}</td>'
            f'<td class="num">{int(r["dt_count"])}</td>'
            f'<td class="num">{int(r["max_board"])}</td>'
            f'<td class="num">{r["seal_rate"]*100:.0f}%</td>'
            f'<td class="num">{r["prem"]:+.1f}%</td>'
            f'<td class="num">{int(r["big_loss"])}</td>'
            f'<td class="num">{r["amount_yi"]:,.0f}</td>'
            f'<td class="num">{r["idx_pct"]:+.2f}%</td></tr>'
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>情绪周期仪表盘 · {last['date']}</title><style>{CSS}</style></head>
<body><div class="wrap">

<header>
  <h1>A股情绪周期仪表盘<span>MARKET SENTIMENT CYCLE</span></h1>
  <div class="meta">数据截止 <b style="color:#c9d1d9">{last['date']}</b>　·　样本 {len(d)} 个交易日　·　股票池 {int(last['stock_n'])} 只<br>
  口径：不复权价判板 · 分位数窗口 {config.PCT_WINDOW} 日 · 温度=六因子加权　{fresh_html}</div>
</header>

{stale_html}

<!-- ========== 跌停分级 ========== -->
<section class="card">
  <h2><span>跌停家数分级 · 买入唯一的刻度</span>
    <span style="margin-left:auto;font-size:12px;color:#6e7681;font-weight:400;letter-spacing:0">
      今日跌停 <b style="color:#2ea88a">{dt_n}</b> 家　大面 <b style="color:#2ea88a">{bl_n}</b> 家　·　{gap_txt}</span></h2>
  <div class="tier">{tier_html}</div>
  <div class="tip" style="margin-top:14px">{verdict}</div>
  <div class="tip" style="margin-top:8px;border-left-color:#2a3b52">
    <b>为什么用跌停家数，不用「温度低」</b>：温度是近 {config.PCT_WINDOW} 日的<b>相对冷热</b>，
    阴跌三个月的市场温度可以不低，横盘反而容易掉到低位，所以「温度低」挑出来的是没人恐慌的日子。
    跌停家数是<b>绝对恐慌</b>——1150 家跌停就是 1150 家，和过去一年什么行情无关。
    历史统计按<b>独立事件</b>算（同一次崩盘的连续几天只计一次），否则一次暴跌能刷出 5 个「成功案例」。</div>
</section>

<!-- ========== 当前状态 ========== -->
<section class="hero">
  <div class="card" style="display:flex;flex-direction:column;align-items:center;justify-content:center">
    {charts.gauge_svg(T, pcol)}
    <div style="font-size:12px;color:#6e7681;margin-top:4px">较前日 {_chg_html(T - prev['score'], 1)}</div>
  </div>

  <div class="card">
    <div class="phase-badge" style="background:{pcol}22;color:{pcol};border:1px solid {pcol}55">
      <span style="width:8px;height:8px;border-radius:50%;background:{pcol};display:inline-block"></span>
      当前阶段
    </div>
    <div class="phase-name" style="color:{pcol}">{pname}</div>
    <div class="phase-sub">已持续 <b style="color:#c9d1d9">{phase_n}</b> 个交易日　·　本轮共 <b style="color:#c9d1d9">{phase_len}</b> 日　·　阶段起点 {d[d['phase_seg']==last['phase_seg']]['date'].iloc[0]}</div>
    <div class="desc">{describe(ph, last)}</div>
  </div>

  <div class="card">
    <h2>今日操作建议</h2>
    <div class="kv"><span class="k">仓位</span><b style="color:{pcol}">{_esc(adv['position'])}</b></div>
    <div class="kv"><span class="k">该做</span><b class="advice-do" style="text-align:right;max-width:230px;font-weight:500;font-size:12.5px">{_esc(adv['do'])}</b></div>
    <div class="kv"><span class="k">别做</span><b class="advice-avoid" style="text-align:right;max-width:230px;font-weight:500;font-size:12.5px">{_esc(adv['avoid'])}</b></div>
    <div class="tip">{_esc(adv['tip'])}</div>
  </div>
</section>

{next_bar}

<!-- ========== 关键指标 ========== -->
<section>
  <div class="grid4">{kpi_html}</div>
</section>

<!-- ========== 温度曲线 ========== -->
<section class="card">
  <h2>情绪温度曲线 · 近 {len(hist_view)} 个交易日</h2>
  {temp_svg}
  <div class="legend">{legend}<span><i style="background:#8b949e"></i>温度5日均</span></div>
</section>

<!-- ========== 分项 ========== -->
<section class="grid2">
  <div class="card">
    <h2>今日六因子拆解（权重 / 得分）</h2>
    {bars}
    <div class="tip" style="margin-top:16px">温度 = 六项得分加权。每项得分是<b>该指标在近 {config.PCT_WINDOW} 个交易日中的百分位</b>，
    所以 70 分意味着「比过去一年 70% 的日子更热」。赚钱效应权重最高（25%），因为它是情绪最灵敏的先行指标。</div>
  </div>
  <div class="card">
    <h2>涨停 / 跌停家数（近 {len(hist_view)} 日）</h2>
    {ztdt_svg}
    <div class="legend"><span><i style="background:#d94b3a"></i>涨停家数</span><span><i style="background:#3f9d8f"></i>跌停家数</span></div>
    <div class="tip" style="margin-top:16px">涨停家数是情绪的「广度」，跌停家数是「杀伤力」。
    两者同时放大 = 剧烈分化（见顶或见底前的特征）。</div>
  </div>
</section>

<section class="grid2">
  <div class="card">
    <h2>近 60 个交易日阶段序列</h2>
    <div class="strip">{strip}</div>
    <div class="legend" style="margin-top:16px">{legend}</div>
    <div class="tip" style="margin-top:16px">每个方块是一个交易日，颜色代表所处阶段（最右为最新）。
    一个完整的情绪周期通常在 15~25 个交易日内走完一圈。</div>
  </div>
  <div class="card">
    <h2>历史上同类阶段的后续表现</h2>
    <table><thead><tr><th>阶段起点</th><th>持续</th><th>结束日</th><th>结束温度</th><th>结束后 5 日等权指数</th></tr></thead>
    <tbody>{hist_rows}</tbody></table>
    <div class="tip" style="margin-top:14px">当前处于「{pname}」，这里是历史上同样进入「{pname}」的最近 6 次，
    以及该阶段结束后 5 个交易日等权指数的涨跌——用来做类比参照。</div>
  </div>
</section>

<!-- ========== 阶段画像 ========== -->
<section class="card">
  <h2>阶段画像 · 六个阶段的历史统计与次日期望</h2>
  <table>
    <thead><tr><th>阶段</th><th>天数</th><th>占比</th><th>出现次数</th><th>平均持续</th><th>最长</th>
    <th>平均温度</th><th>次日指数均值</th><th>次日涨停均值</th><th>次日溢价均值</th><th>次日温度变化</th></tr></thead>
    <tbody>{st_rows}</tbody>
  </table>
  <div class="tip">读法：「次日表现」= 处于该阶段的那一天，<b>下一个交易日</b>的市场表现。若某阶段的次日指数均值明显为负、次日温度变化明显为负，说明该阶段确实是<b>减仓信号</b>；反之是加仓窗口。这张表就是情绪周期是否有效的直接证据。</div>
</section>

<!-- ========== 明细 ========== -->
<section class="card">
  <h2>最近 40 个交易日明细</h2>
  <table>
    <thead><tr><th>日期</th><th style="text-align:left">阶段</th><th>温度</th><th>涨停</th><th>跌停</th><th>最高板</th>
    <th>封板率</th><th>昨涨停溢价</th><th>大面</th><th>成交(亿)</th><th>上证</th></tr></thead>
    <tbody>{det_rows}</tbody>
  </table>
</section>

<footer>
<b>口径说明</b><br>
1. 涨跌停按<b>不复权价</b>判定（主板 10%、创业板/科创板 20%、ST 5%），并校验涨幅接近板幅以排除除权误判。<br>
2. 剔除 ST、上市不足 {config.EXCLUDE_NEW_DAYS} 个交易日的次新、停牌日、1 元以下个股。<br>
3. 温度 = 涨停强度 20% + 封板质量 15% + 赚钱效应 25% + 亏钱效应 20% + 市场广度 10% + 量能 10%；
   每个因子先转成<b>滚动 {config.PCT_WINDOW} 日分位数</b>再加权，解决上市公司变多导致的家数不可比问题。<br>
4. 阶段由状态机逐日推进，带粘性（不恶化不切换）；高潮/冰点为单日事件信号，其余需动量确认。<br>
5. ST 状态用当前名称近似历史，个别股票早期 ST 属性可能不准，影响极小（ST 已被剔除）。<br>
<b>风险提示</b>：情绪指标是概率工具，不是预测工具。任何阶段都可能被突发消息打断，仓位管理优先于信号判断。
</footer>
</div></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
