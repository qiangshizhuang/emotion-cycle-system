# -*- coding: utf-8 -*-
"""第二层验证：情绪周期对「打板/题材」的指导力 + 按信号调仓的净值表现。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
import config

d = pd.read_csv("reports/情绪周期_逐日明细_含前瞻收益.csv", encoding="utf-8-sig")
v = d[d["phase_valid"] == True].copy()

# 打板收益代理：今日买入「昨日涨停股」，次日卖出 → 收益 = 次日 prem
v["prem_next"] = v["prem"].shift(-1)
v["prem_next2"] = v["prem"].shift(-2)

print("=== 阶段 → 次日「昨涨停股」平均收益（打板选手真实收益）===")
rows = []
for ph in ["FREEZE","REPAIR","FERMENT","CLIMAX","DIVERGE","EBB"]:
    g = v[v["phase"] == ph]
    p = g["prem_next"].dropna()
    rows.append({"阶段": config.PHASES[ph]["name"], "天数": len(p),
                 "次日打板收益%": round(p.mean(), 2),
                 "胜率%": round((p > 0).mean() * 100, 1),
                 "中位%": round(p.median(), 2),
                 "最差%": round(p.min(), 2)})
t = pd.DataFrame(rows)
print(t.to_string(index=False))
print(f"\n全样本次日打板收益 {v['prem_next'].mean():.2f}%，胜率 {(v['prem_next']>0).mean()*100:.1f}%")

print("\n=== 温度分箱 → 次日打板收益 ===")
v["tb"] = pd.cut(v["score"], [0,20,40,60,80,100], labels=["0-20","20-40","40-60","60-80","80-100"])
g = v.groupby("tb", observed=True).agg(天数=("score","size"),
        次日打板收益=("prem_next","mean"), 胜率=("prem_next", lambda s:(s>0).mean()*100))
print(g.round(2).to_string())

# ---------------- 仓位策略回测 ----------------
print("\n=== 按信号调仓回测（等权指数，收盘执行，无未来函数）===")
df = d.copy().reset_index(drop=True)
df["ret"] = df["eq_ret"] / 100.0                     # 当日等权收益

# 信号用「前一日」的状态决定「今日」仓位
sig_temp = df["score_ema3"].shift(1)
pos_temp = np.where(sig_temp >= 60, 1.0, np.where(sig_temp >= 40, 0.5, 0.0))
ph_prev = df["phase"].shift(1)
pos_phase = np.where(ph_prev.isin(["FERMENT","CLIMAX"]), 1.0,
             np.where(ph_prev.isin(["REPAIR","DIVERGE"]), 0.4, 0.0))

def stat(pos, name):
    p = pd.Series(pos, index=df.index).fillna(0)
    r = p * df["ret"]
    nav = (1 + r).cumprod()
    yrs = len(df) / 244
    cagr = nav.iloc[-1] ** (1/yrs) - 1
    dd = (nav / nav.cummax() - 1).min()
    sharpe = r.mean() / (r.std() + 1e-12) * np.sqrt(244)
    return {"策略": name, "总收益%": round((nav.iloc[-1]-1)*100,1), "年化%": round(cagr*100,1),
            "最大回撤%": round(dd*100,1), "夏普": round(sharpe,2),
            "日均仓位%": round(p.mean()*100,0), "胜率%": round((r[r!=0]>0).mean()*100,1)}

res = [stat(np.ones(len(df)), "基准：满仓等权"),
       stat(pos_temp, "温度>60满仓 / 40-60半仓 / <40空仓"),
       stat(pos_phase, "发酵·高潮满仓 / 修复·分歧4成 / 冰点·退潮空仓")]
bt = pd.DataFrame(res)
print(bt.to_string(index=False))
bt.to_csv("reports/情绪周期_仓位策略对比.csv", index=False, encoding="utf-8-sig")

# 年度表现
print("\n=== 分年度（策略 vs 基准）===")
df["y"] = df["date"].str[:4]
df["p_temp"] = pd.Series(pos_temp, index=df.index).fillna(0)
df["p_phase"] = pd.Series(pos_phase, index=df.index).fillna(0)
for y, gg in df.groupby("y"):
    b = (1 + gg["ret"]).prod() - 1
    a = (1 + gg["p_temp"]*gg["ret"]).prod() - 1
    c = (1 + gg["p_phase"]*gg["ret"]).prod() - 1
    print(f"{y}: 基准 {b*100:+6.1f}% | 温度仓位 {a*100:+6.1f}% | 阶段仓位 {c*100:+6.1f}%")

# 保存带信号的明细
df["pos_temp"] = df["p_temp"]; df["pos_phase"] = df["p_phase"]
df.drop(columns=["y","p_temp","p_phase"]).to_csv(
    "reports/情绪周期_逐日明细_含前瞻收益.csv", index=False, encoding="utf-8-sig")
print("\n已更新明细 CSV")
