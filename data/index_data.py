# -*- coding: utf-8 -*-
"""指数数据抓取（上证指数 / 创业板指）"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import runtime

CACHE_DIR = runtime.cache_dir()

INDEXES = {"sh000001": "上证指数", "sz399006": "创业板指"}


def fetch_index(symbol="sh000001", start=None, end=None):
    import akshare as ak
    p = os.path.join(CACHE_DIR, f"index_{symbol}.parquet")
    df = ak.stock_zh_index_daily(symbol=symbol)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df.to_parquet(p, index=False)
    return df


def load_index(symbol="sh000001"):
    p = os.path.join(CACHE_DIR, f"index_{symbol}.parquet")
    if os.path.exists(p):
        return pd.read_parquet(p)
    return fetch_index(symbol)


if __name__ == "__main__":
    for s in INDEXES:
        d = fetch_index(s)
        print(s, len(d), d["date"].iloc[-1])
