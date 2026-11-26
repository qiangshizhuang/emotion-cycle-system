# -*- coding: utf-8 -*-
"""指数数据抓取（上证指数 / 创业板指）"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import runtime

CACHE_DIR = runtime.cache_dir()

INDEXES = {"sh000001": "上证指数", "sz399006": "创业板指"}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch_index(symbol="sh000001", start=None, end=None):
    from data import akcompat
    p = os.path.join(CACHE_DIR, f"index_{symbol}.parquet")
    df = akcompat.index_daily(symbol)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df.to_parquet(p, index=False)
    return df


def _today_bar(symbol):
    """
    用实时行情取当日收盘 K 线。

    指数日线接口当天收盘后要过很久才更新（个股已经有今天，指数还停在昨天），
    结果仪表盘上「上证指数」显示成一个破折号。实时接口收盘后立刻就是收盘价，
    补这一根只要 1 次请求。
    """
    import requests
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={symbol}",
            headers={"Referer": "https://finance.sina.com.cn", "User-Agent": UA},
            timeout=8,
        )
        r.encoding = "gbk"
        if '"' not in r.text:
            return None
        f = r.text.split('"')[1].split(",")
        if len(f) < 32:
            return None
        day, hm = f[30].strip(), f[31].strip()
        # 盘中不补：那根 K 线还没走完，写进去就是假收盘价
        if not day or hm < "15:00":
            return None
        o, c, h, l = float(f[1]), float(f[3]), float(f[4]), float(f[5])
        if c <= 0 or h < l:
            return None
        return {"date": day, "open": o, "high": h, "low": l, "close": c,
                "volume": float(f[8] or 0)}
    except Exception:
        return None


def _append_today(df, symbol):
    """把当日收盘那根补进缓存（仅当缓存还没有这一天）。"""
    bar = _today_bar(symbol)
    if not bar or not len(df) or bar["date"] <= df["date"].max():
        return df
    # 成交量单位在不同指数上不一致（手 / 股），按量级自动对齐，避免 100 倍误差
    lastv = float(df["volume"].iloc[-1]) if "volume" in df else 0
    if lastv > 0 and bar["volume"] > 0 and lastv / bar["volume"] > 20:
        bar["volume"] *= 100
    out = pd.concat([df, pd.DataFrame([bar])], ignore_index=True)
    try:
        out.to_parquet(os.path.join(CACHE_DIR, f"index_{symbol}.parquet"), index=False)
    except Exception:
        pass
    return out


def load_index(symbol="sh000001", refresh=True):
    """
    读取指数日线；缓存落后于今天时自动重抓，并用实时行情补上当天那一根。

    这一步不能省：交易日历（align_trade_day）依赖它判断「今天收盘了没」，
    指数缓存不刷新就会永远停在旧日期，收盘后运行也补不上当天数据。
    """
    import time
    p = os.path.join(CACHE_DIR, f"index_{symbol}.parquet")
    if not os.path.exists(p):
        return _append_today(fetch_index(symbol), symbol)
    df = pd.read_parquet(p)
    if not refresh:
        return df
    today = time.strftime("%Y-%m-%d")
    if df["date"].max() < today:
        # 10 分钟节流，避免短时间内反复请求；失败重试两次再放弃
        if (time.time() - os.path.getmtime(p)) > 600:
            for _ in range(2):
                try:
                    df = fetch_index(symbol)
                    break
                except Exception:
                    time.sleep(1)
    return _append_today(df, symbol)


if __name__ == "__main__":
    for s in INDEXES:
        d = fetch_index(s)
        print(s, len(d), d["date"].iloc[-1])
