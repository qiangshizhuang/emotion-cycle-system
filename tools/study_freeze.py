# -*- coding: utf-8 -*-
"""冰点到底能不能买：分级、确认信号、可执行规则回测。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
import config

d = pd.read_csv("reports/情绪周期_逐日明细_含前瞻收益.csv", encoding="utf-8-sig")
d = d.sort_values("date").reset_index(drop=True)
v = d[d["phase_valid"] == True].copy()

# 统一口径：信号日收盘决策，次日收盘买入，持有 h 日
for h in (3, 5, 10, 20):
    d[f"buy{h}"] = (d["eq_index"].shift(-(1 + h)) / d["eq_index"].shift(-1) - 1) * 100
d["buy5_dd"] = np.nan
v = d[d["phase_valid"] == True].copy()

def stat(mask, label, col="buy5", base=None):
    g = v[mask]
    s = g[col].dropna()
    if len(s) == 0:
        return {"规则": label, "次数": 0}
    return {"规则": label, "次数": len(s),
            "5日均%": round(g["buy5"].mean(), 2), "5日胜率%": round((g["buy5"] > 0).mean() * 100, 0),
            "10日均%": round(g["buy10"].mean(), 2), "10日胜率%": round((g["buy10"] > 0).mean() * 100, 0),
            "20日均%": round(g["buy20"].mean(), 2), "最差5日%": round(g["buy5"].min(), 1)}

print("=" * 96)
print("【一】冰点按「深度」分级：是不是越冰越该买？")
print("=" * 96)
rows = []
for lo, hi in [(0, 10), (10, 20), (20, 30), (30, 45)]:
    m = (v["score"] >= lo) & (v["score"] < hi)
    rows.append(stat(m, f"温度 {lo}-{hi}"))
print(pd.DataFrame(rows).to_string(index=False))

print()
print("按跌停家数分级（当日跌停数）")
rows = []
for lo, hi in [(0, 20), (20, 60), (60, 150), (150, 400), (400, 3000)]:
    m = (v["dt_count"] >= lo) & (v["dt_count"] < hi)
    rows.append(stat(m, f"跌停 {lo}-{hi}"))
print(pd.DataFrame(rows).to_string(index=False))

print()
print("按大面家数分级（跌幅>7%且未跌停）")
rows = []
for lo, hi in [(0, 100), (100, 400), (400, 900), (900, 4000)]:
    m = (v["big_loss"] >= lo) & (v["big_loss"] < hi)
    rows.append(stat(m, f"大面 {lo}-{hi}"))
print(pd.DataFrame(rows).to_string(index=False))

print()
print("=" * 96)
print("【二】冰点日 vs 冰点后的「确认日」：买左边还是买右边？")
print("=" * 96)
# 标记：处于冰点段（phase=FREEZE）
v["is_freeze"] = v["phase"] == "FREEZE"
# 冰点段内的最后一天（次日就要离开冰点）
v["freeze_end"] = v["is_freeze"] & (~v["is_freeze"].shift(-1).fillna(False).astype(bool))
# 冰点后首个「涨停>=80 且 溢价>0」的确认日
v["confirm"] = False
idx = v.index.tolist()
for i in idx:
    if not v.loc[i, "is_freeze"]:
        continue
    # 从冰点段结束往后找 10 天内第一个确认日
    seg_end = i
    while seg_end + 1 < len(v) and v.loc[seg_end + 1, "is_freeze"]:
        seg_end += 1
    for j in range(seg_end + 1, min(seg_end + 11, len(v))):
        if v.loc[j, "zt_count"] >= 80 and (v.loc[j, "prem"] or 0) > 0:
            v.loc[j, "confirm"] = True
            break

rows = [
    stat(v["is_freeze"], "冰点当天（买在左侧）"),
    stat(v["freeze_end"], "冰点段最后一天"),
    stat(v["confirm"], "冰点后首个确认日（涨停≥80 且溢价>0）"),
    stat(v["is_freeze"] | v["confirm"], "冰点日 + 确认日 全买"),
]
print(pd.DataFrame(rows).to_string(index=False))

print()
print("=" * 96)
print("【三】可执行规则回测（信号次日收盘买入）")
print("=" * 96)
rules = {
    "R1 温度<10 当天买": (v["score"] < 10),
    "R2 温度<15 且 跌停>100": (v["score"] < 15) & (v["dt_count"] > 100),
    "R3 温度<10 且 大面>800": (v["score"] < 10) & (v["big_loss"] > 800),
    "R4 冰点后确认（涨停≥80且溢价>0，且在冰点/退潮后10日内）": v["confirm"],
    "R5 温度从<25 上穿 30": (v["score"] >= 30) & (v["score"].shift(1) < 25),
    "R6 温度<20 且 溢价>0（冰点区转暖）": (v["score"] < 20) & (v["prem"] > 0),
}
rows = [stat(m, k) for k, m in rules.items()]
print(pd.DataFrame(rows).to_string(index=False))

print()
print("=" * 96)
print("【四】如果按「冰点分批建仓」做：温度越低仓位越重，退潮清仓")
print("=" * 96)
pos = np.where(v["score_ema3"] < 10, 1.0,
      np.where(v["score_ema3"] < 20, 0.8,
      np.where(v["score_ema3"] < 35, 0.5, 0.0)))
v["p"] = pd.Series(pos, index=v.index).shift(1).fillna(0)   # 前一日温度决定今日仓位
r = v["p"] * v["eq_ret"] / 100
nav = (1 + r).cumprod()
base = (1 + v["eq_ret"] / 100).cumprod()
print(f"抄底策略：总收益 {(nav.iloc[-1]-1)*100:+.1f}%  最大回撤 {(nav/nav.cummax()-1).min()*100:.1f}%  日均仓位 {v['p'].mean()*100:.0f}%")
print(f"满仓基准：总收益 {(base.iloc[-1]-1)*100:+.1f}%  最大回撤 {(base/base.cummax()-1).min()*100:.1f}%")

print()
print("=" * 96)
print("【五】高潮卖出检验：高潮当天清仓 vs 高潮后转分歧再清仓")
print("=" * 96)
v["is_climax"] = v["phase"] == "CLIMAX"
v["climax_end"] = v["is_climax"] & (~v["is_climax"].shift(-1).fillna(False).astype(bool))
rows = [
    stat(v["is_climax"], "高潮当天卖出后的市场收益（T+1起）"),
    stat(v["climax_end"], "高潮段最后一天卖出"),
    stat((v["phase"] == "DIVERGE") & (v["phase"].shift(1) == "CLIMAX"), "高潮转分歧那天卖出"),
]
print(pd.DataFrame(rows).to_string(index=False))
print("（若为负，说明卖对了；为正，说明卖早了）")
