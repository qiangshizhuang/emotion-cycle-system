# -*- coding: utf-8 -*-
"""导出台账：逐日指标 + 阶段统计 + 极值核验（xlsx，带阶段配色）。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import config

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(BASE, "reports")
d = pd.read_csv(os.path.join(R, "情绪周期_逐日明细_含前瞻收益.csv"), encoding="utf-8-sig")
v = d[d["phase_valid"] == True].copy()

PCX = {"FREEZE": "1B3A5C", "REPAIR": "2E7D8F", "FERMENT": "B87A24",
       "CLIMAX": "B03A2E", "DIVERGE": "6C4A8C", "EBB": "4A5568"}

thin = Side(style="thin", color="D5DBE3")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
HDR_FILL = PatternFill("solid", fgColor="1F2937")
HDR_FONT = Font(color="FFFFFF", bold=True, size=10.5)

wb = Workbook()

# ---------------- Sheet1 逐日台账 ----------------
ws = wb.active
ws.title = "逐日情绪指标"
cols = [
    ("日期", "date", 11), ("阶段", "phase_name", 9), ("温度", "score", 7),
    ("涨停家数", "zt_count", 9), ("跌停家数", "dt_count", 9), ("炸板家数", "zb_count", 9),
    ("封板率", "seal_rate", 8), ("最高连板", "max_board", 9), ("涨停溢价%", "prem", 10),
    ("大面家数", "big_loss", 9), ("上涨占比", "breadth", 9), ("等权涨幅%", "eq_ret", 10),
    ("等权指数", "eq_index", 10), ("上证收盘", "idx_close", 10), ("上证涨幅%", "idx_pct", 10),
    ("后5日%", "eq_f5", 9), ("后10日%", "eq_f10", 9),
]
ws.append([c[0] for c in cols])
for i, (_, _, w) in enumerate(cols, 1):
    ws.column_dimensions[get_column_letter(i)].width = w
    c = ws.cell(row=1, column=i)
    c.fill = HDR_FILL; c.font = HDR_FONT
    c.alignment = Alignment(horizontal="center", vertical="center")
ws.freeze_panes = "C2"
ws.row_dimensions[1].height = 26

rows = v.sort_values("date").values.tolist()
si = {c[1]: i for i, c in enumerate(cols)}
for r in v.sort_values("date").itertuples(index=False):
    ws.append([
        r.date, r.phase_name, round(float(r.score), 0),
        int(r.zt_count), int(r.dt_count), int(r.zb_count),
        round(float(r.seal_rate) * 100, 0) if pd.notna(r.seal_rate) else None,
        int(r.max_board),
        round(float(r.prem), 2) if pd.notna(r.prem) else None,
        int(r.big_loss),
        round(float(r.breadth) * 100, 0) if pd.notna(r.breadth) else None,
        round(float(r.eq_ret), 2), round(float(r.eq_index), 1),
        round(float(r.idx_close), 1) if pd.notna(r.idx_close) else None,
        round(float(r.idx_pct), 2) if pd.notna(r.idx_pct) else None,
        round(float(r.eq_f5), 2) if pd.notna(r.eq_f5) else None,
        round(float(r.eq_f10), 2) if pd.notna(r.eq_f10) else None,
    ])

n = ws.max_row
for row in ws.iter_rows(min_row=2, max_row=n, max_col=len(cols)):
    for c in row:
        c.border = BORDER
        c.font = Font(size=10)
        c.alignment = Alignment(horizontal="center" if c.column not in (1,) else "center")
    ph = row[1].value
    if ph:
        key = next((k for k, v2 in config.PHASES.items() if v2["name"] == ph), None)
        if key:
            row[1].fill = PatternFill("solid", fgColor=PCX[key])
            row[1].font = Font(size=10, bold=True, color="FFFFFF")
    for idx in (8, 11, 14, 15, 16):   # 溢价 / 等权 / 上证 / 后5 / 后10
        c = row[idx]
        if isinstance(c.value, (int, float)):
            c.number_format = "0.00"
            c.font = Font(size=10, color="C0392B" if c.value > 0 else ("1E8449" if c.value < 0 else "666666"))
    row[0].font = Font(size=10, bold=False)

ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{n}"

# ---------------- Sheet2 阶段统计 ----------------
ws2 = wb.create_sheet("阶段赔率")
rows2 = []
for ph in ["FREEZE", "REPAIR", "FERMENT", "CLIMAX", "DIVERGE", "EBB"]:
    g = v[v["phase"] == ph]
    rows2.append([config.PHASES[ph]["name"], len(g), round(len(g) / len(v) * 100, 1),
                  round(g["score"].mean(), 1),
                  round(g["eq_f1"].mean(), 2), round((g["eq_f1"] > 0).mean() * 100, 1),
                  round(g["eq_f5"].mean(), 2), round((g["eq_f5"] > 0).mean() * 100, 1),
                  round(g["eq_f10"].mean(), 2), round((g["eq_f10"] > 0).mean() * 100, 1),
                  round(g["eq_f5"].min(), 2), round(g["eq_f5"].max(), 2),
                  round(g["eq_dd5"].mean(), 2)])
h2 = ["阶段", "天数", "占比%", "均温", "次日均%", "次日胜率%", "5日均%", "5日胜率%",
      "10日均%", "10日胜率%", "5日最差%", "5日最好%", "5日均回撤%"]
ws2.append(h2)
for i, h in enumerate(h2, 1):
    c = ws2.cell(row=1, column=i)
    c.fill = HDR_FILL; c.font = HDR_FONT
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws2.column_dimensions[get_column_letter(i)].width = 12
for r in rows2:
    ws2.append(r)
    rr = ws2.max_row
    key = next(k for k, v2 in config.PHASES.items() if v2["name"] == r[0])
    ws2.cell(row=rr, column=1).fill = PatternFill("solid", fgColor=PCX[key])
    ws2.cell(row=rr, column=1).font = Font(color="FFFFFF", bold=True, size=10.5)
    for i in range(1, len(h2) + 1):
        cc = ws2.cell(row=rr, column=i)
        cc.border = BORDER
        cc.alignment = Alignment(horizontal="center")
        if i >= 5 and isinstance(cc.value, (int, float)):
            cc.number_format = "0.00"
            cc.font = Font(size=10.5, color="C0392B" if cc.value > 0 else ("1E8449" if cc.value < 0 else "666666"))

ws2.append([])
ws2.append(["说明", "「后 N 日」＝当日收盘持有到 N 个交易日后的等权指数收益，事后统计，用于验证而非交易信号。"])
ws2.append(["", "等权指数＝全部 5223 只股票等权，基点 1000，比上证更贴近题材股体感。"])
ws2.append(["", "温度 0-100，由涨停强度/封板质量/赚钱效应/亏钱效应/市场广度/量能六因子分位加权。"])
ws2.cell(row=ws2.max_row - 2, column=1).font = Font(bold=True, size=10)

# ---------------- Sheet3 极值核验 ----------------
ws3 = wb.create_sheet("极值日核验")
h3 = ["类型", "日期", "系统判定", "当日等权%", "涨停", "跌停", "大面", "溢价%", "温度", "后5日%", "后10日%"]
ws3.append(h3)
for i, h in enumerate(h3, 1):
    c = ws3.cell(row=1, column=i)
    c.fill = HDR_FILL; c.font = HDR_FONT
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws3.column_dimensions[get_column_letter(i)].width = 12

def add(df, label):
    for r in df.itertuples(index=False):
        ws3.append([label, r.date, r.phase_name, round(float(r.eq_ret), 2),
                    int(r.zt_count), int(r.dt_count), int(r.big_loss),
                    round(float(r.prem), 1) if pd.notna(r.prem) else None,
                    round(float(r.score), 0),
                    round(float(r.eq_f5), 1) if pd.notna(r.eq_f5) else None,
                    round(float(r.eq_f10), 1) if pd.notna(r.eq_f10) else None])
        rr = ws3.max_row
        key = next(k for k, v2 in config.PHASES.items() if v2["name"] == r.phase_name)
        ws3.cell(row=rr, column=3).fill = PatternFill("solid", fgColor=PCX[key])
        ws3.cell(row=rr, column=3).font = Font(color="FFFFFF", bold=True, size=10)
        for i in range(1, len(h3) + 1):
            ws3.cell(row=rr, column=i).border = BORDER
            ws3.cell(row=rr, column=i).alignment = Alignment(horizontal="center")

add(v.nsmallest(8, "eq_ret"), "跌幅前8")
add(v.nlargest(8, "eq_ret"), "涨幅前8")

out = os.path.join(R, "情绪周期_逐日台账.xlsx")
wb.save(out)
print("OK", out, f"{n-1} 行")
