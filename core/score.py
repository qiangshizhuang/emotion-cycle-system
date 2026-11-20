# -*- coding: utf-8 -*-
"""
打分模块：把绝对家数转成「滚动分位数」，再加权成 0~100 的情绪温度。
为什么用分位数：A 股十年间上市公司从 2500 家到 5400 家，涨停 60 家在 2016 是高潮、
在 2026 只是日常。绝对值不可比，分位数才可比。
"""
import numpy as np
import pandas as pd

import config


def pct_rank(s, window=None, min_periods=None):
    """滚动分位数（0~100）：当前值在过去 window 日中的百分位。"""
    window = window or config.PCT_WINDOW
    min_periods = min_periods or config.PCT_MIN_PERIODS
    r = s.rolling(window, min_periods=min_periods).rank(pct=True)
    return (r * 100).clip(0, 100)


def compute_score(out, smooth=3):
    """
    计算六个分项得分与综合温度。
    smooth：因子平滑窗口。原始家数日间噪声极大（利好日 100 家、次日 30 家），
    直接取分位会让温度一天跳 40 分，失去指导意义。先做轻度 EMA 再取分位。
    """
    d = out.copy()

    def sm(series, span=None):
        return series.ewm(span=span or smooth, adjust=False).mean()

    # 1) 涨停强度
    d["s_limit_up"] = pct_rank(sm(d["zt_count"].astype(float)))

    # 2) 封板质量 = 封板率分位 与 连板高度分位 各半
    seal = d["seal_rate"].fillna(d["seal_rate"].median())
    s_seal = pct_rank(sm(seal))
    s_maxb = pct_rank(sm(d["max_board"].astype(float)))
    d["s_seal_quality"] = 0.5 * s_seal + 0.5 * s_maxb

    # 3) 赚钱效应：昨涨停今日平均溢价（越高越好）
    prem = d["prem"].fillna(0)
    d["s_money_effect"] = pct_rank(sm(prem))

    # 4) 亏钱效应（反向）：跌停家数 + 大面数
    s_dt = pct_rank(sm(d["dt_count"].astype(float)))
    s_bl = pct_rank(sm(d["big_loss"].astype(float)))
    d["s_loss_effect"] = 100 - (0.6 * s_dt + 0.4 * s_bl)

    # 5) 市场广度
    d["s_breadth"] = pct_rank(d["breadth"].fillna(0.5))

    # 6) 量能
    d["s_volume"] = pct_rank(d["amt_ratio"].fillna(1.0))

    w = config.SCORE_WEIGHTS
    d["score"] = (
        w["limit_up"] * d["s_limit_up"]
        + w["seal_quality"] * d["s_seal_quality"]
        + w["money_effect"] * d["s_money_effect"]
        + w["loss_effect"] * d["s_loss_effect"]
        + w["breadth"] * d["s_breadth"]
        + w["volume"] * d["s_volume"]
    )

    # 平滑温度（判定用），抑制单日噪声；原始 score 用于展示波动
    d["score_ema3"] = d["score"].ewm(span=5, adjust=False).mean()
    d["score_ma5"] = d["score"].rolling(5, min_periods=1).mean()
    d["score_chg"] = d["score"] - d["score"].shift(1)
    d["score_chg5"] = d["score"] - d["score"].shift(5)

    # 辅助分位（供状态机使用，同样平滑）
    d["zt_pct"] = pct_rank(sm(d["zt_count"].astype(float)))
    d["dt_pct"] = pct_rank(sm(d["dt_count"].astype(float)))
    d["bl_pct"] = pct_rank(sm(d["big_loss"].astype(float)))
    d["prem_pct"] = pct_rank(sm(prem))
    return d
