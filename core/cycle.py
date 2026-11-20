# -*- coding: utf-8 -*-
"""
状态机：把连续的温度值切成六个离散阶段。
设计原则
1. 阶段有「粘性」——不满足恶化条件就维持原阶段，避免每天跳变；
2. 循环顺序固定：冰点→修复→发酵→高潮→分歧→退潮→冰点，允许跳级（高潮可直接到退潮）；
3. 高潮/冰点是「事件型」信号（单日确认，因为尖顶尖底），其余需动量确认。
"""
import numpy as np
import pandas as pd

import config


def _decide(prev, r):
    T = r["score_ema3"]
    dT5 = r["score_chg5"] if pd.notna(r["score_chg5"]) else 0.0
    prem = r["prem"] if pd.notna(r["prem"]) else 0.0
    zt_p = r["zt_pct"] if pd.notna(r["zt_pct"]) else 50.0
    dt_p = r["dt_pct"] if pd.notna(r["dt_pct"]) else 50.0
    seal = r["seal_rate"] if pd.notna(r["seal_rate"]) else 0.6
    maxb = r["max_board"] if pd.notna(r["max_board"]) else 0

    # ---------- 事件型信号（优先级最高）----------
    # 冰点：温度极低 + 跌停集中，或跌停分位极端且涨停萎缩
    if (T <= config.T_FREEZE and dt_p >= 50) or (dt_p >= 85 and zt_p <= 30):
        return "FREEZE"
    # 高潮：温度极热 + 涨停爆量/溢价爆表；或涨停分位极端 + 高度打开
    # 注意：必须叠加温度门槛 T>=62。否则「冰点后的超跌反弹」（如 2024-02-07 涨停 98 家、溢价 7%）
    # 会被误判成高潮，而它其实是修复的第一天。
    if T >= config.T_HOT and (zt_p >= 85 or prem >= 5):
        return "CLIMAX"
    if zt_p >= 92 and prem >= 4 and maxb >= 5 and T >= 62:
        return "CLIMAX"

    # ---------- 退潮 ----------
    if prem <= config.EBB_PREM and dt_p >= 50:
        return "EBB"
    if prev in ("FERMENT", "CLIMAX", "DIVERGE") and dT5 <= -12 and prem < 0:
        return "EBB"

    # ---------- 按前态做转移 ----------
    if prev == "CLIMAX":
        if prem < 0:
            return "DIVERGE" if prem > config.EBB_PREM else "EBB"
        if dT5 < -6:
            return "DIVERGE"
        return "CLIMAX"

    if prev == "FERMENT":
        if prem <= config.EBB_PREM:
            return "EBB"
        if prem < config.DIVERGE_PREM and seal < 0.65:
            return "DIVERGE"
        if T < 45:
            return "DIVERGE"
        return "FERMENT"

    if prev == "DIVERGE":
        if prem <= config.EBB_PREM or T < 35:
            return "EBB"
        if T >= 68 and prem > 1:
            return "FERMENT"          # 分歧转一致，二波
        return "DIVERGE"

    if prev == "EBB":
        if T <= 22:
            return "FREEZE"
        if dT5 > 3 and prem > -2:
            return "REPAIR"
        return "EBB"

    if prev == "FREEZE":
        if T >= 55 and prem > 0 and maxb >= 3:
            return "FERMENT"
        if T >= 26 and dT5 > 2:
            return "REPAIR"
        return "FREEZE"

    # 前态为空或 REPAIR
    if T >= 55 and prem > 0 and maxb >= 3:
        return "FERMENT"
    if T >= 26 and dT5 > 0:
        return "REPAIR"
    if T <= 22:
        return "FREEZE"
    return prev or "REPAIR"


def _is_forced(prev, cur, r):
    """强制切换：只有极端事件才允许打断最小驻留。"""
    prem = r["prem"] if pd.notna(r["prem"]) else 0.0
    zt_p = r["zt_pct"] if pd.notna(r["zt_pct"]) else 50.0
    dt_p = r["dt_pct"] if pd.notna(r["dt_pct"]) else 50.0
    if cur == "CLIMAX" and zt_p >= 92 and prem >= 4:
        return True
    if cur == "FREEZE" and dt_p >= 90:
        return True
    if cur == "EBB" and prem <= -5 and dt_p >= 70:
        return True
    return False


def detect_phase(df, min_dwell=None):
    """逐日推进状态机。min_dwell：阶段最小驻留天数（抑制来回抖动）。"""
    min_dwell = config.MIN_DWELL_DAYS if min_dwell is None else min_dwell
    d = df.reset_index(drop=True).copy()
    phases = []
    prev = None
    dwell = 0
    for _, r in d.iterrows():
        cur = _decide(prev, r)
        if prev is not None and cur != prev and dwell < min_dwell and not _is_forced(prev, cur, r):
            cur = prev          # 未满足驻留条件，维持原阶段
        dwell = dwell + 1 if cur == prev else 1
        phases.append(cur)
        prev = cur
    d["phase"] = phases
    d["phase_name"] = d["phase"].map(lambda p: config.PHASES[p]["name"])
    d["phase_color"] = d["phase"].map(lambda p: config.PHASES[p]["color"])
    d["phase_order"] = d["phase"].map(lambda p: config.PHASES[p]["order"])

    # 预热期分位数不可靠，标记
    d.loc[: config.PCT_MIN_PERIODS, ["phase", "phase_name", "phase_color"]] = None
    d["phase_valid"] = d["phase"].notna()

    # 段编号：同一阶段连续为一段
    seg = (d["phase"] != d["phase"].shift(1)).cumsum()
    d["phase_seg"] = seg
    d["phase_day_n"] = d.groupby("phase_seg").cumcount() + 1
    d["phase_len"] = d.groupby("phase_seg")["phase"].transform("size")
    return d


def phase_stats(d):
    """阶段画像：出现次数、平均持续、次日期望表现。"""
    v = d[d["phase_valid"]].copy()
    v["next_idx_pct"] = v["idx_pct"].shift(-1)
    v["next_zt"] = v["zt_count"].shift(-1)
    v["next_prem"] = v["prem"].shift(-1)
    v["next_score"] = v["score"].shift(-1)

    rows = []
    for ph, g in v.groupby("phase"):
        segs = g.groupby("phase_seg").size()
        rows.append({
            "阶段": config.PHASES[ph]["name"],
            "code": ph,
            "天数": len(g),
            "占比%": round(len(g) / len(v) * 100, 1),
            "出现次数": len(segs),
            "平均持续": round(segs.mean(), 1),
            "最长持续": int(segs.max()),
            "平均温度": round(g["score"].mean(), 1),
            "次日指数均值%": round(g["next_idx_pct"].mean(), 2),
            "次日涨停均值": round(g["next_zt"].mean(), 0),
            "次日溢价均值%": round(g["next_prem"].mean(), 2),
            "次日温度变化": round((g["next_score"] - g["score"]).mean(), 1),
        })
    res = pd.DataFrame(rows).sort_values("code", key=lambda s: s.map(
        lambda x: config.PHASES[x]["order"]))
    return res


def transition_prob(d, from_phase=None):
    """
    阶段转移概率：历史上处于 from_phase 的交易日，次日进入各阶段的频率。
    直接回答「现在这个阶段，明天大概率往哪走」。
    """
    v = d[d["phase_valid"]].copy()
    v["next_phase"] = v["phase"].shift(-1)
    v = v.dropna(subset=["next_phase"])
    if from_phase:
        v = v[v["phase"] == from_phase]
    m = pd.crosstab(v["phase"], v["next_phase"], normalize="index") * 100
    order = [k for k, _ in sorted(config.PHASES.items(), key=lambda kv: kv[1]["order"])]
    m = m.reindex(index=[o for o in order if o in m.index],
                  columns=[o for o in order if o in m.columns]).fillna(0)
    return m.round(1)
