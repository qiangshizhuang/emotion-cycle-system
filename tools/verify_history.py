# -*- coding: utf-8 -*-
"""历史准确性验证：逐日指标 + 阶段前瞻收益 + 命中率 + 关键节点回溯。"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
import config

STAMP = None

def load():
    f = sorted([x for x in os.listdir("reports") if x.startswith("情绪周期_每日指标_")])[-1]
    d = pd.read_csv(os.path.join("reports", f), encoding="utf-8-sig")
    STAMP = f.split("_")[-1].replace(".csv", "")
    return d

def add_forward(d, horizons=(1, 3, 5, 10)):
    d = d.copy()
    for h in horizons:
        d[f"eq_f{h}"] = (d["eq_index"].shift(-h) / d["eq_index"] - 1) * 100
        d[f"idx_f{h}"] = (d["idx_close"].shift(-h) / d["idx_close"] - 1) * 100
        # 未来 h 日内的最大回撤（对持仓者最痛的点）
        fwd_max = pd.concat([(d["eq_index"].shift(-k) / d["eq_index"] - 1) * 100
                             for k in range(1, h + 1)], axis=1).min(axis=1)
        fwd_min_ret = pd.concat([(d["eq_index"].shift(-k) / d["eq_index"] - 1) * 100
                                 for k in range(1, h + 1)], axis=1).max(axis=1)
        d[f"eq_dd{h}"] = fwd_max
        d[f"eq_up{h}"] = fwd_min_ret
    return d

def main():
    d = load()
    d = add_forward(d)
    v = d[d["phase_valid"] == True].copy()
    print(f"样本 {len(v)} 个有效交易日  {v['date'].min()} ~ {v['date'].max()}")
    print()

    # ---------- 1. 阶段前瞻收益 ----------
    rows = []
    for ph in ["FREEZE", "REPAIR", "FERMENT", "CLIMAX", "DIVERGE", "EBB"]:
        g = v[v["phase"] == ph]
        r = {"阶段": config.PHASES[ph]["name"], "天数": len(g), "占比%": round(len(g)/len(v)*100,1),
             "温度": round(g["score"].mean(),1)}
        for h in (1,3,5,10):
            r[f"T+{h}均%"] = round(g[f"eq_f{h}"].mean(), 2)
            r[f"T+{h}胜率%"] = round((g[f"eq_f{h}"] > 0).mean()*100, 1)
        r["T+5中位%"] = round(g["eq_f5"].median(), 2)
        r["T+5最差%"] = round(g["eq_f5"].min(), 2)
        r["T+5最好%"] = round(g["eq_f5"].max(), 2)
        r["未来5日均回撤%"] = round(g["eq_dd5"].mean(), 2)
        r["未来10日均回撤%"] = round(g["eq_dd10"].mean(), 2)
        rows.append(r)
    tab = pd.DataFrame(rows)
    print("=== 按阶段的前瞻收益（等权指数）===")
    print(tab.to_string(index=False))
    print()

    # ---------- 2. 单调性检验 ----------
    ordmap = {k: config.PHASES[k]["order"] for k in config.PHASES}
    v["porder"] = v["phase"].map(ordmap)
    v["temp_bin"] = pd.cut(v["score"], [0,20,40,60,80,100], labels=["0-20","20-40","40-60","60-80","80-100"])
    print("=== 温度分箱 vs 未来收益（看单调性）===")
    tb = v.groupby("temp_bin", observed=True).agg(
        天数=("score","size"), 温度=("score","mean"),
        T1=("eq_f1","mean"), T3=("eq_f3","mean"), T5=("eq_f5","mean"), T5胜率=("eq_f5", lambda s:(s>0).mean()*100))
    print(tb.round(2).to_string())
    print()

    # ---------- 3. 方向命中率 ----------
    stance = {"FREEZE": 1, "REPAIR": 1, "FERMENT": 1, "DIVERGE": 0, "EBB": -1, "CLIMAX": -1}
    v["stance"] = v["phase"].map(stance)
    m = v.dropna(subset=["eq_f1"])
    s = m[m["stance"] != 0]
    hit = ((s["stance"] == 1) & (s["eq_f1"] > 0)) | ((s["stance"] == -1) & (s["eq_f1"] < 0))
    print(f"=== 方向命中率（次日等权指数）===")
    print(f"有立场天数 {len(s)}，命中 {hit.sum()}，命中率 {hit.mean()*100:.1f}%")
    print(f"看多组({(s['stance']==1).sum()}天) 次日均收益 {s[s['stance']==1]['eq_f1'].mean():.2f}%，胜率 {(s[s['stance']==1]['eq_f1']>0).mean()*100:.1f}%")
    print(f"看空组({(s['stance']==-1).sum()}天) 次日均收益 {s[s['stance']==-1]['eq_f1'].mean():.2f}%，下跌概率 {(s[s['stance']==-1]['eq_f1']<0).mean()*100:.1f}%")
    print(f"全部样本次日均收益 {m['eq_f1'].mean():.2f}%，基准上涨概率 {(m['eq_f1']>0).mean()*100:.1f}%")
    print()

    # ---------- 4. 首日进入某阶段的后续表现（事件研究）----------
    print("=== 阶段切换首日（事件研究）===")
    v["new_phase"] = v["phase"] != v["phase"].shift(1)
    for ph in ["FREEZE","CLIMAX","EBB","FERMENT"]:
        g = v[(v["new_phase"]) & (v["phase"] == ph)]
        print(f"进入{config.PHASES[ph]['name']:2s} {len(g):3d} 次 | 当日T+1 {g['eq_f1'].mean():+.2f}% "
              f"T+3 {g['eq_f3'].mean():+.2f}% T+5 {g['eq_f5'].mean():+.2f}% T+10 {g['eq_f10'].mean():+.2f}% "
              f"| T+5胜率 {(g['eq_f5']>0).mean()*100:.0f}%")
    print()

    # ---------- 5. 分年度稳定性 ----------
    v["year"] = v["date"].str[:4]
    print("=== 分年度 T+5 收益（稳定性检查）===")
    pv = v.pivot_table(index="year", columns="phase", values="eq_f5", aggfunc="mean").round(2)
    pv = pv.reindex(columns=["FREEZE","REPAIR","FERMENT","CLIMAX","DIVERGE","EBB"])
    print(pv.to_string())
    print()
    pv2 = v.pivot_table(index="year", columns="phase", values="eq_f5", aggfunc="size")
    pv2 = pv2.reindex(columns=["FREEZE","REPAIR","FERMENT","CLIMAX","DIVERGE","EBB"])
    print(pv2.to_string())
    print()

    # ---------- 6. 极值日回溯 ----------
    print("=== 系统判「高潮」全部日期 ===（可逐日核对）")
    cx = v[v["phase"] == "CLIMAX"]
    print(cx[["date","score","zt_count","dt_count","seal_rate","max_board","prem","eq_f5","eq_f10"]].round(1).to_string(index=False))
    print()
    print("=== 系统判「冰点」全部日期 ===")
    fz = v[v["phase"] == "FREEZE"]
    print(fz[["date","score","zt_count","dt_count","seal_rate","max_board","prem","eq_f5","eq_f10"]].round(1).to_string(index=False))
    print()

    # 保存
    d.to_csv("reports/情绪周期_逐日明细_含前瞻收益.csv", index=False, encoding="utf-8-sig")
    tab.to_csv("reports/情绪周期_阶段前瞻收益.csv", index=False, encoding="utf-8-sig")
    print("已保存")

if __name__ == "__main__":
    main()
