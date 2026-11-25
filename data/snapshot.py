# -*- coding: utf-8 -*-
"""
全市场单日快照（新浪批量行情接口）

为什么需要它
------------
新浪的日线接口只能逐只股票取，5223 只就是 5223 次请求，无论并发怎么调都要三四分钟。
而批量行情接口一次能拿 800 只的当日行情——补「今天」这一天只需要十来次请求。

所以增量更新分两条路：
  只差今天  → 走批量快照，约 10 秒
  差了多天  → 退回逐只抓（有进度条，可被时间预算打断）

接口：https://hq.sinajs.cn/list=sh600000,sz000001,...
限制：必须带 Referer，返回 GBK，只能取到当日（收盘后即当日收盘价）。
"""
import re
import time
import requests
import pandas as pd

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
URL = "https://hq.sinajs.cn/list="
BATCH = 500

_PAT = re.compile(r'hq_str_([a-z]{2}\d{6})="([^"]*)"')


def _parse(text):
    """把 var hq_str_xxx="..." 解析成记录列表。字段位置见模块注释。"""
    out = []
    for code, payload in _PAT.findall(text):
        f = payload.split(",")
        if len(f) < 33:          # 字段不足说明是空壳或已退市
            continue
        try:
            day = f[30].strip()
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
                continue
            o, pre, close = float(f[1]), float(f[2]), float(f[3])
            hi, lo = float(f[4]), float(f[5])
            vol, amt = float(f[8]), float(f[9])
        except (ValueError, IndexError):
            continue
        # 停牌：现价为 0 或当日无成交，写入会污染涨跌停判定
        if close <= 0 or o <= 0 or vol <= 0:
            continue
        out.append({
            "date": day, "code": code, "open": o, "high": hi,
            "low": lo, "close": close, "volume": vol, "amount": amt,
        })
    return out


def fetch_day(codes, expect_date=None, batch=BATCH, retries=2):
    """
    抓一批股票的最新一个交易日行情。

    expect_date：期望的日期（YYYY-MM-DD）。传了就只保留这一天的记录，
    并且在拿不到时返回空表——避免把「昨天的数据」当成今天写进库。
    """
    rows = []
    chunks = [codes[i:i + batch] for i in range(0, len(codes), batch)]
    sess = requests.Session()
    sess.headers.update({"Referer": "https://finance.sina.com.cn", "User-Agent": UA})

    for i, ch in enumerate(chunks):
        for attempt in range(retries + 1):
            try:
                r = sess.get(URL + ",".join(ch), timeout=15)
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                r.encoding = "gbk"
                rows.extend(_parse(r.text))
                break
            except Exception:
                if attempt >= retries:
                    pass
                time.sleep(0.5)
        if i and i % 4 == 0:
            print(f"    快照 {min(i * batch, len(codes))}/{len(codes)}", flush=True)

    df = pd.DataFrame(rows, columns=["date", "code", "open", "high", "low",
                                     "close", "volume", "amount"])
    if len(df) and expect_date:
        df = df[df["date"] == expect_date]
    return df


def is_today_close(date_str, now=None):
    """判断某个日期是不是「今天且已收盘」。收盘后批量快照才等于当日日线。"""
    now = now or time.localtime()
    today = time.strftime("%Y-%m-%d", now)
    return date_str == today and time.strftime("%H:%M", now) >= "15:05"
