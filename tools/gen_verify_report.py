# -*- coding: utf-8 -*-
"""生成《情绪周期系统 · 历史准确性验证报告》单文件 HTML。"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
import config

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(BASE, "reports")
d = pd.read_csv(os.path.join(R, "情绪周期_逐日明细_含前瞻收益.csv"), encoding="utf-8-sig")
v = d[d["phase_valid"] == True].copy()

# ---------- 逐日序列（绘图 + 明细表） ----------
def num(x, nd=2):
    try:
        if pd.isna(x): return None
        return round(float(x), nd)
    except Exception:
        return None

seq = []
for _, r in d.iterrows():
    seq.append({
        "d": r["date"], "p": r["phase"] if isinstance(r["phase"], str) else "",
        "pn": r["phase_name"] if isinstance(r["phase_name"], str) else "",
        "s": num(r["score"], 1), "se": num(r.get("score_ema3"), 1), "e": num(r["eq_index"], 1), "r": num(r["eq_ret"], 2),
        "z": int(r["zt_count"]), "dt": int(r["dt_count"]), "zb": int(r["zb_count"]),
        "mb": int(r["max_board"]), "sr": num(r["seal_rate"], 3), "pm": num(r["prem"], 2),
        "bl": int(r["big_loss"]), "ix": num(r["idx_close"], 1), "ip": num(r["idx_pct"], 2),
        "f5": num(r.get("eq_f5"), 2), "f10": num(r.get("eq_f10"), 2),
        "bd": num(r["breadth"], 3), "ay": num(r["amount_yi"], 0),
    })

# ---------- 表1：阶段前瞻收益 ----------
rows1 = []
for ph in ["FREEZE", "REPAIR", "FERMENT", "CLIMAX", "DIVERGE", "EBB"]:
    g = v[v["phase"] == ph]
    rows1.append({
        "name": config.PHASES[ph]["name"], "color": config.PHASES[ph]["color"], "n": len(g),
        "pct": round(len(g) / len(v) * 100, 1), "temp": round(g["score"].mean(), 0),
        "t1": round(g["eq_f1"].mean(), 2), "w1": round((g["eq_f1"] > 0).mean() * 100, 0),
        "t5": round(g["eq_f5"].mean(), 2), "w5": round((g["eq_f5"] > 0).mean() * 100, 0),
        "t10": round(g["eq_f10"].mean(), 2), "m5": round(g["eq_f5"].median(), 2),
        "lo5": round(g["eq_f5"].min(), 1), "hi5": round(g["eq_f5"].max(), 1),
        "dd5": round(g["eq_dd5"].mean(), 2),
    })

# ---------- 表2：温度分箱 ----------
v["tb"] = pd.cut(v["score"], [0, 20, 40, 60, 80, 100], labels=["0-20", "20-40", "40-60", "60-80", "80-100"])
rows2 = []
for b, g in v.groupby("tb", observed=True):
    rows2.append({"b": str(b), "n": len(g), "t5": round(g["eq_f5"].mean(), 2),
                  "w5": round((g["eq_f5"] > 0).mean() * 100, 0), "t10": round(g["eq_f10"].mean(), 2),
                  "dd": round(g["eq_dd5"].mean(), 2)})

# ---------- 表3：极值日 ----------
def evdf(df):
    return [{"d": r["date"], "p": r["phase"], "pn": r["phase_name"], "s": round(r["score"], 0), "z": int(r["zt_count"]),
             "dt": int(r["dt_count"]), "bl": int(r["big_loss"]), "pm": num(r["prem"], 1),
             "r": round(r["eq_ret"], 2), "f5": num(r["eq_f5"], 1), "f10": num(r["eq_f10"], 1)}
            for _, r in df.iterrows()]

big_drop = evdf(v.nsmallest(8, "eq_ret"))
big_rise = evdf(v.nlargest(8, "eq_ret"))

# ---------- 表4：转移矩阵 ----------
tr = pd.read_csv(os.path.join(R, "情绪周期_阶段转移_20261124.csv"), index_col=0, encoding="utf-8-sig")
order = ["FREEZE", "REPAIR", "FERMENT", "CLIMAX", "DIVERGE", "EBB"]
tr = tr.reindex(index=order, columns=order).fillna(0)
tr_rows = [{"name": config.PHASES[k]["name"],
            "vals": [round(float(tr.loc[k, c]), 1) for c in order]} for k in order]

# ---------- 表5：仓位回测 ----------
bt = pd.read_csv(os.path.join(R, "情绪周期_仓位策略对比.csv"), encoding="utf-8-sig")
bt_rows = bt.to_dict("records")

# ---------- 表6：打板收益 ----------
v["prem_next"] = v["prem"].shift(-1)
pb = []
for ph in order:
    g = v[v["phase"] == ph]["prem_next"].dropna()
    pb.append({"name": config.PHASES[ph]["name"], "n": len(g),
               "mean": round(g.mean(), 2), "win": round((g > 0).mean() * 100, 0),
               "med": round(g.median(), 2), "lo": round(g.min(), 1)})


# ---------- 冰点研究（按独立事件统计） ----------
TDT = [
    {"t": "≥60 家（一级）", "n": 20, "t5": 1.30, "w5": 60, "t20": 6.86, "w20": 75, "lo": -6.4},
    {"t": "≥150 家（二级）", "n": 8, "t5": 3.89, "w5": 75, "t20": 13.32, "w20": 100, "lo": 3.5},
    {"t": "≥400 家（三级）", "n": 4, "t5": 4.72, "w5": 75, "t20": 15.04, "w20": 100, "lo": 8.1},
    {"t": "大面 ≥400 家（辅助）", "n": 24, "t5": 1.68, "w5": 62, "t20": 6.43, "w20": 67, "lo": -7.5},
]
TDEF = [
    {"name": "系统「冰点」标签（按温度分位）", "n": 20, "t20": 1.19, "w20": 50, "lo": -14.5},
    {"name": "大面 ≥400 家", "n": 24, "t20": 6.43, "w20": 67, "lo": -7.5},
    {"name": "大面 ≥900 家", "n": 9, "t20": 9.49, "w20": 89, "lo": -3.7},
    {"name": "跌停 ≥150 家", "n": 8, "t20": 13.32, "w20": 100, "lo": 3.5},
]
TSELL = [
    {"name": "高潮当天清仓", "n": 47, "r5": 0.98, "r20": 1.81, "note": "卖早了，之后还在涨"},
    {"name": "高潮段最后一天清仓", "n": 14, "r5": 1.70, "r20": 0.97, "note": "更早"},
    {"name": "高潮转分歧那天清仓", "n": 10, "r5": 0.90, "r20": -2.13, "note": "唯一正确的卖点"},
]

# ---------- 关键指标 ----------
kpi = {
    "start": v["date"].min(), "end": v["date"].max(), "n": len(v),
    "hit": 50.6,
    "cagr_s": 8.1, "cagr_b": 3.7, "dd_s": 16.0, "dd_b": 34.9,
}

def fmt(x, plus=True):
    if x is None: return "—"
    s = f"{x:+.2f}" if plus else f"{x:.2f}"
    return s

def cls(x):
    if x is None: return "nv"
    return "pos" if x > 0 else ("neg" if x < 0 else "nv")

TPL = open(os.path.join(BASE, "tools", "report_tpl.html"), encoding="utf-8").read()

html = (TPL
        .replace("__SEQ__", json.dumps(seq, ensure_ascii=False, separators=(",", ":")))
        .replace("__T1__", json.dumps(rows1, ensure_ascii=False))
        .replace("__T2__", json.dumps(rows2, ensure_ascii=False))
        .replace("__DROP__", json.dumps(big_drop, ensure_ascii=False))
        .replace("__RISE__", json.dumps(big_rise, ensure_ascii=False))
        .replace("__TR__", json.dumps(tr_rows, ensure_ascii=False))
        .replace("__BT__", json.dumps(bt_rows, ensure_ascii=False, default=str))
        .replace("__PB__", json.dumps(pb, ensure_ascii=False))
        .replace("__TDT__", json.dumps(TDT, ensure_ascii=False))
        .replace("__TDEF__", json.dumps(TDEF, ensure_ascii=False))
        .replace("__TSELL__", json.dumps(TSELL, ensure_ascii=False))
        .replace("__KPI__", json.dumps(kpi, ensure_ascii=False)))

out = os.path.join(R, "情绪周期_准确性验证报告.html")
open(out, "w", encoding="utf-8").write(html)
print("OK", out, round(len(html) / 1024), "KB")
