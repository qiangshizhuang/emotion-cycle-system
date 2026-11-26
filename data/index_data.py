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
    from data import akcompat
    p = os.path.join(CACHE_DIR, f"index_{symbol}.parquet")
    df = akcompat.index_daily(symbol)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df.to_parquet(p, index=False)
    return df


def load_index(symbol="sh000001", refresh=True):
    """
    读取指数日线；缓存落后于今天时自动重抓一次。

    这一步不能省：交易日历（align_trade_day）依赖它判断「今天收盘了没」，
    指数缓存不刷新就会永远停在旧日期，收盘后运行也补不上当天数据。
    """
    import time
    p = os.path.join(CACHE_DIR, f"index_{symbol}.parquet")
    if os.path.exists(p):
        df = pd.read_parquet(p)
        if not refresh:
            return df
        today = time.strftime("%Y-%m-%d")
        stale = df["date"].max() < today
        # 10 分钟节流，避免短时间内反复请求；失败重试两次再放弃
        if stale and (time.time() - os.path.getmtime(p)) > 600:
            for _ in range(2):
                try:
                    return fetch_index(symbol)
                except Exception:
                    time.sleep(1)
            return df
        return df
    return fetch_index(symbol)


if __name__ == "__main__":
    for s in INDEXES:
        d = fetch_index(s)
        print(s, len(d), d["date"].iloc[-1])
