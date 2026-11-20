# -*- coding: utf-8 -*-
"""
指标层：由全市场日线计算「每日情绪指标」
所有涨跌停判定均基于不复权价，符合交易所规则。
"""
import numpy as np
import pandas as pd

import config


def _limit_pct(code, is_st):
    """按板块返回涨跌停幅度。"""
    c6 = code[2:] if code[:2] in ("sh", "sz") else code
    if is_st:
        # 主板 ST 5%；创业板/科创板 ST 仍为 20%
        if c6.startswith(("30", "688")):
            return 0.20
        return 0.05
    if c6.startswith("688"):
        return 0.20
    if c6.startswith(("300", "301")):
        return 0.20
    if c6.startswith(("8", "4", "920")):
        return 0.30
    return 0.10


def build_daily_flags(daily, stock_list):
    """
    逐股逐日标注：涨跌幅、是否涨停/炸板/跌停、连板数。
    返回带标志的全市场长表。
    """
    df = daily.copy()
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    st_map = dict(zip(stock_list["code"], stock_list["is_st"]))
    name_map = dict(zip(stock_list["code"], stock_list["name"]))

    df["is_st"] = df["code"].map(st_map).fillna(False).astype(bool)
    df["name"] = df["code"].map(name_map).fillna("")

    # 前收盘（同一股票上一交易日收盘）
    df["preclose"] = df.groupby("code")["close"].shift(1)
    df["pct"] = (df["close"] / df["preclose"] - 1) * 100

    # 涨跌停价
    lp = df.apply(lambda r: _limit_pct(r["code"], r["is_st"]), axis=1)
    df["limit_pct"] = lp
    up_p = (df["preclose"] * (1 + df["limit_pct"])).round(2)
    dn_p = (df["preclose"] * (1 - df["limit_pct"])).round(2)
    df["up_price"] = up_p
    df["dn_price"] = dn_p

    tol = config.LIMIT_TOL
    # 涨停方向校验：涨幅须接近 +板幅，用于排除除权造成的假信号
    near_up = (df["pct"] - df["limit_pct"] * 100).abs() <= 2.0
    # 跌停方向校验：涨幅须接近 -板幅（关键：方向不能搞反）
    near_dn = (df["pct"] + df["limit_pct"] * 100).abs() <= 2.0
    # 涨停：收盘价触及涨停价
    df["is_zt"] = ((df["close"] >= df["up_price"] - tol) & near_up).fillna(False)
    # 炸板：盘中触及涨停但收盘未封住（收盘涨幅可以远低于板幅，不能用 near_up 约束）
    df["is_zb"] = ((df["high"] >= df["up_price"] - tol) & (~df["is_zt"]) & (df["pct"] > 0)).fillna(False)
    # 跌停
    df["is_dt"] = ((df["close"] <= df["dn_price"] + tol) & near_dn).fillna(False)

    df["is_zt"] = df["is_zt"].fillna(False)
    df["is_dt"] = df["is_dt"].fillna(False)

    # 连板数：连续涨停天数（非涨停为 0）
    notzt = (~df["is_zt"]).astype(int)
    df["grp"] = notzt.groupby(df["code"]).cumsum()
    df["board"] = df.groupby(["code", "grp"])["is_zt"].cumsum().astype(int)

    # 上市天数（用于剔除次新）
    df["listed_n"] = df.groupby("code").cumcount()
    first_dates = df.groupby("code")["date"].transform("min")
    data_start = df["date"].min()
    is_old = first_dates <= data_start
    df["is_new"] = (~is_old) & (df["listed_n"] < config.EXCLUDE_NEW_DAYS)

    df["big_loss"] = (df["pct"] <= config.BIG_LOSS_PCT) & (~df["is_dt"])

    return df


def daily_sentiment(df, exclude_st=True):
    """聚合为每日情绪指标表。"""
    d = df.dropna(subset=["preclose"]).copy()
    if exclude_st and config.EXCLUDE_ST:
        d = d[~d["is_st"]]
    d = d[d["close"] >= config.MIN_PRICE]
    d = d[~d["is_new"]]
    d = d[d["volume"].fillna(0) > 0]

    g = d.groupby("date")
    out = pd.DataFrame({
        "zt_count":   g["is_zt"].sum(),
        "dt_count":   g["is_dt"].sum(),
        "zb_count":   g["is_zb"].sum(),
        "max_board":  g["board"].max(),
        "board2":     g.apply(lambda x: (x["board"] >= 2).sum(), include_groups=False),
        "board3":     g.apply(lambda x: (x["board"] >= 3).sum(), include_groups=False),
        "up_count":   g.apply(lambda x: (x["pct"] > 0).sum(), include_groups=False),
        "down_count": g.apply(lambda x: (x["pct"] < 0).sum(), include_groups=False),
        "flat_count": g.apply(lambda x: (x["pct"] == 0).sum(), include_groups=False),
        "big_loss":   g["big_loss"].sum(),
        "amount":     g["amount"].sum(),
        "stock_n":    g["code"].count(),
        "eq_ret":     g["pct"].mean(),          # 全市场等权平均涨幅（比上证更贴近题材股情绪）
        "eq_ret_med": g["pct"].median(),
    })
    out = out.reset_index().sort_values("date").reset_index(drop=True)

    # 等权指数（基点 1000）：情绪周期的「真实载体」，上证被权重股绑架，无法反映小票情绪
    out["eq_index"] = (1 + out["eq_ret"] / 100).cumprod() * 1000

    # 封板率
    touched = out["zt_count"] + out["zb_count"]
    out["seal_rate"] = np.where(touched > 0, out["zt_count"] / touched, np.nan)

    # 市场广度
    act = out["up_count"] + out["down_count"]
    out["breadth"] = np.where(act > 0, out["up_count"] / act, np.nan)

    # ---- 赚钱效应：昨日涨停股，今日平均涨跌幅（记到「今日」）----
    all_dates = out["date"].tolist()
    nxt = {all_dates[i]: all_dates[i + 1] for i in range(len(all_dates) - 1)}
    zt_codes = d.loc[d["is_zt"], ["date", "code"]].copy()
    zt_codes["next_date"] = zt_codes["date"].map(nxt)
    nxt_perf = d[["date", "code", "pct", "is_dt"]].rename(columns={"date": "next_date"})
    m = zt_codes.merge(nxt_perf, on=["next_date", "code"], how="left").dropna(subset=["pct"])
    prem = (m.groupby("next_date")
             .agg(prem=("pct", "mean"),
                  prem_win=("pct", lambda s: (s > 0).mean() * 100),
                  prem_dt=("is_dt", "sum"),
                  prem_n=("pct", "size"))
             .reset_index().rename(columns={"next_date": "date"}))
    out = out.merge(prem, on="date", how="left")

    # 成交额 20 日均值比
    out["amt_ma20"] = out["amount"].rolling(20, min_periods=5).mean()
    out["amt_ratio"] = out["amount"] / out["amt_ma20"]

    # 连板晋级率：今日 >=2 板家数 / 昨日涨停家数
    out["promo_rate"] = out["board2"].shift(0) / out["zt_count"].shift(1)
    out["promo_rate"] = out["promo_rate"].clip(0, 2)

    out["amount_yi"] = out["amount"] / 1e8
    return out


def add_index(out, index_df):
    """合并指数涨跌幅与位置。"""
    idx = index_df.copy()
    idx = idx.rename(columns={"close": "idx_close"})
    idx["idx_pct"] = idx["idx_close"].pct_change() * 100
    idx["idx_ma20"] = idx["idx_close"].rolling(20).mean()
    idx["idx_dev"] = (idx["idx_close"] / idx["idx_ma20"] - 1) * 100
    keep = idx[["date", "idx_close", "idx_pct", "idx_ma20", "idx_dev"]]
    return out.merge(keep, on="date", how="left")
