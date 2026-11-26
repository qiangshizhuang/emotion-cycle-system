# -*- coding: utf-8 -*-
"""
快速增量接口（新浪 K 线，按根数取数）

为什么单独写一个
----------------
原来的 stock_zh_a_hist_sina 每次都返回**全部历史**（约 700 根），单只 ~70ms，
10 并发实测只有 13 只/秒——补一天要 400 秒，任何预算都撑不住，超时就写进半截数据。

这个接口用 datalen 只取最近 N 根，返回体小一个数量级，实测 177 只/秒，
5223 只补最近 5 天约 30 秒。

字段差异：K 线接口不返回成交额，用 volume × 均价估算。
成交额只参与「量能」这一个因子（权重 10%）且是分位比较，估算误差不影响结论。
"""
import time
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://finance.sina.com.cn"}
KEEP_COLS = ["date", "code", "open", "high", "low", "close", "volume", "amount"]

_session = None


def _sess():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


def fetch_one(code, datalen=10, retries=2):
    """取单只最近 datalen 根日线，返回 DataFrame 或 None。"""
    s = _sess()
    for i in range(retries):
        try:
            r = s.get(URL, params={"symbol": code, "scale": 240, "ma": "no",
                                   "datalen": int(datalen)}, timeout=12)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            j = r.json()
            if not j:
                return None
            d = pd.DataFrame(j)
            d["code"] = code
            for c in ("open", "high", "low", "close", "volume"):
                d[c] = pd.to_numeric(d[c], errors="coerce")
            d = d.rename(columns={"day": "date"})
            d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
            # 成交额估算：股数 × 均价（均价取 (高+低+收)/3）
            d["amount"] = d["volume"] * ((d["high"] + d["low"] + d["close"]) / 3).fillna(d["close"])
            return d[KEEP_COLS]
        except Exception:
            time.sleep(0.25 + i * 0.35)
    return None


def fetch_recent(codes, datalen=10, workers=10, budget=None, label="补数据", quiet=False):
    """
    并发取最近 datalen 根。返回 (长表, 失败数)。

    budget 超时会带着已有数据返回，由调用方决定写不写——调用方必须先校验覆盖率。
    """
    rows, fail = [], 0
    t0 = time.time()
    timed_out = False
    total = len(codes)
    step = max(total // 20, 1)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_one, c, datalen): c for c in codes}
        done = 0
        for f in as_completed(futs):
            done += 1
            if budget and (time.time() - t0) > budget:
                timed_out = True
                break
            try:
                r = f.result()
            except Exception:
                r = None
            if r is None or len(r) == 0:
                fail += 1
            else:
                rows.append(r)
            if not quiet and (done % step == 0 or done == total):
                pct = done / total * 100
                rate = done / max(time.time() - t0, 0.01)
                print(f"  {label} {done}/{total} ({pct:.0f}%)  {rate:.0f} 只/秒", flush=True)
        ex.shutdown(wait=False, cancel_futures=True)

    got = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=KEEP_COLS)
    if timed_out and not quiet:
        print(f"  已达时间预算，本次取到 {got['code'].nunique() if len(got) else 0} 只", flush=True)
    return got, fail


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import runtime
    lst = pd.read_csv(os.path.join(runtime.cache_dir(), "stock_list.csv"), dtype={"code": str})
    t = time.time()
    d, f = fetch_recent(lst["code"].tolist()[:300], datalen=5)
    print(d.head(), len(d), "fail", f, f"{time.time()-t:.1f}s")
