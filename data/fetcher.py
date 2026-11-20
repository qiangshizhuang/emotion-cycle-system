# -*- coding: utf-8 -*-
"""
数据层：全 A 股日线抓取（新浪源，不复权）
- 支持多线程并发 + 分片落盘 + 断点续传
- 也可切换为读取本地通达信导出 CSV（见 load_from_local_csv）
"""
import os
import json
import time
import glob
import random
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import runtime

CACHE_DIR = runtime.cache_dir()

KEEP_COLS = ["date", "code", "open", "high", "low", "close", "volume", "amount"]


def _log(msg, logfile=None):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if logfile:
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def get_stock_list(use_cache=True):
    """获取沪深 A 股列表（含是否 ST）。"""
    p = os.path.join(CACHE_DIR, "stock_list.csv")
    if use_cache and os.path.exists(p) and (time.time() - os.path.getmtime(p) < 86400 * 3):
        return pd.read_csv(p, dtype={"code": str})

    import akshare as ak
    spot = ak.stock_zh_a_spot()
    spot = spot.rename(columns={"代码": "code", "名称": "name"})
    spot["code"] = spot["code"].astype(str)
    # 只保留沪深（剔除 bj），主板+创业板+科创板
    df = spot[spot["code"].str.match(r"^(sh|sz)")].copy()
    df["code_6"] = df["code"].str[2:]
    df = df[df["code_6"].str.match(r"^(60|68|00|30)")]
    df["is_st"] = df["name"].astype(str).str.upper().str.contains("ST")
    # 剔除退市整理、B股等
    df = df[~df["name"].astype(str).str.contains("退")]
    out = df[["code", "name", "code_6", "is_st"]].reset_index(drop=True)
    out.to_csv(p, index=False, encoding="utf-8-sig")
    return out


def _fetch_one(code, start, end, retries=3):
    import akshare as ak
    for i in range(retries):
        try:
            d = ak.stock_zh_a_daily(symbol=code, start_date=start, end_date=end, adjust="")
            if d is None or len(d) == 0:
                return None
            d = d.copy()
            d["code"] = code
            d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
            for c in ["open", "high", "low", "close", "volume", "amount"]:
                if c in d:
                    d[c] = pd.to_numeric(d[c], errors="coerce")
                else:
                    d[c] = 0.0
            return d[KEEP_COLS]
        except Exception:
            time.sleep(0.8 + random.random())
    return None


def fetch_all(start=None, end=None, workers=8):
    """抓取全市场日线，分片写入 parquet，支持断点续传。"""
    start = start or config.DATA_START
    end = end or time.strftime("%Y-%m-%d")
    tag = f"{start.replace('-', '')}_{end.replace('-', '')}"
    logf = os.path.join(CACHE_DIR, f"fetch_{tag}.log")

    lst = get_stock_list()
    todo = [c for c in lst["code"].tolist() if pd.to_numeric(lst.loc[lst["code"] == c, "code_6"], errors="coerce").notna().any()]
    codes = lst["code"].tolist()
    _log(f"股票池 {len(codes)} 只（沪深A）", logf)

    shard_size = 400
    shards = [codes[i:i + shard_size] for i in range(0, len(codes), shard_size)]
    _log(f"分 {len(shards)} 片，每片 {shard_size} 只，并发 {workers}", logf)

    for si, shard in enumerate(shards):
        sp = os.path.join(CACHE_DIR, f"shard_{tag}_{si:03d}.parquet")
        if os.path.exists(sp):
            continue
        rows, fail = [], 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_fetch_one, c, start, end): c for c in shard}
            for f in as_completed(futs):
                r = f.result()
                if r is None:
                    fail += 1
                else:
                    rows.append(r)
        if rows:
            pd.concat(rows, ignore_index=True).to_parquet(sp, index=False)
        _log(f"分片 {si + 1}/{len(shards)} 完成：成功 {len(rows)}，失败 {fail}", logf)

    # 合并
    files = sorted(glob.glob(os.path.join(CACHE_DIR, f"shard_{tag}_*.parquet")))
    _log(f"合并 {len(files)} 个分片...", logf)
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    out = os.path.join(CACHE_DIR, f"daily_all_{tag}.parquet")
    df.to_parquet(out, index=False)
    _log(f"总行数 {len(df)}，股票 {df['code'].nunique()} 只 -> {out}", logf)
    return out


def load_daily(start=None, end=None):
    """读取已缓存的日线；不存在则自动抓取。"""
    start = start or config.DATA_START
    end = end or time.strftime("%Y-%m-%d")
    tag = f"{start.replace('-', '')}_{end.replace('-', '')}"
    out = os.path.join(CACHE_DIR, f"daily_all_{tag}.parquet")
    if not os.path.exists(out):
        fetch_all(start, end)
    return pd.read_parquet(out)


# ============ 增量更新（日常使用） ============
DAILY_CACHE = os.path.join(CACHE_DIR, "daily_all.parquet")


def align_trade_day(end):
    """把 end 对齐到最近一个已收盘的交易日（解决周末/盘前运行白跑的问题）。"""
    try:
        from data import index_data
        idx = index_data.load_index("sh000001")
        days = sorted([d for d in idx["date"].tolist() if d <= end])
        if not days:
            return end
        last_day = days[-1]
        # 若 end 就是今天且尚未收盘，退一交易日
        today = time.strftime("%Y-%m-%d")
        if end == today and time.strftime("%H:%M") < "15:10":
            prev = [d for d in days if d < end]
            return prev[-1] if prev else last_day
        return last_day
    except Exception:
        return end


def _fetch_range(codes, start, end, workers=8, logf=None):
    """并发抓取指定区间，返回长表。"""
    rows, fail = [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one, c, start, end): c for c in codes}
        for f in as_completed(futs):
            r = f.result()
            if r is None:
                fail += 1
            else:
                rows.append(r)
    if logf:
        _log(f"  区间 {start}~{end}：成功 {len(rows)} 只，无数据 {fail} 只", logf)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=KEEP_COLS)


def update(start=None, end=None, workers=8, full=False):
    """
    增量更新本地日线库（cache/daily_all.parquet）。
    日常只需抓「库里最后一天 +1」到今天，几分钟内完成。
    """
    start = start or config.DATA_START
    end = end or time.strftime("%Y-%m-%d")
    logf = os.path.join(CACHE_DIR, "update.log")
    lst = get_stock_list(use_cache=not full)
    codes = lst["code"].tolist()

    if full or not os.path.exists(DAILY_CACHE):
        _log(f"全量抓取 {start} ~ {end}，股票 {len(codes)} 只", logf)
        df = _fetch_range(codes, start, end, workers, logf)
        df = df.drop_duplicates(["code", "date"]).sort_values(["code", "date"])
        df.to_parquet(DAILY_CACHE, index=False)
        _log(f"完成：{len(df):,} 行 / {df['code'].nunique()} 只", logf)
        return df

    end = align_trade_day(end)
    old = pd.read_parquet(DAILY_CACHE)
    last = old["date"].max()
    if last >= end:
        _log(f"缓存已是最新（{last}），无需更新", logf)
        return old

    nxt = (pd.Timestamp(last) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    _log(f"增量抓取 {nxt} ~ {end}（库内已有至 {last}）", logf)
    new = _fetch_range(codes, nxt, end, workers, logf)
    if len(new) == 0:
        _log("无新增数据（可能非交易日）", logf)
        return old
    df = pd.concat([old, new], ignore_index=True).drop_duplicates(["code", "date"])
    df = df.sort_values(["code", "date"])
    df.to_parquet(DAILY_CACHE, index=False)
    _log(f"完成：新增 {len(df) - len(old):,} 行，总计 {len(df):,} 行", logf)
    return df


def load(start=None, end=None, auto_update=True):
    """统一读取入口：优先用本地库，必要时增量更新。"""
    start = start or config.DATA_START
    end = end or time.strftime("%Y-%m-%d")
    if auto_update:
        df = update(start, end)
    elif os.path.exists(DAILY_CACHE):
        df = pd.read_parquet(DAILY_CACHE)
    else:
        df = update(start, end, full=True)
    return df[(df["date"] >= start) & (df["date"] <= end)].copy()


def load_from_local_csv(root_dir):
    """
    读取本地通达信导出日线 CSV。
    root_dir 下每个 csv 一个股票，文件名含 6 位代码；列名支持通达信默认中文表头。
    """
    files = glob.glob(os.path.join(root_dir, "**", "*.csv"), recursive=True)
    frames = []
    for fp in files:
        base = os.path.basename(fp)
        code6 = "".join([ch for ch in base if ch.isdigit()])[:6]
        if len(code6) != 6:
            continue
        d = None
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
            try:
                d = pd.read_csv(fp, encoding=enc, on_bad_lines="skip")
                break
            except Exception:
                d = None
        if d is None or d.shape[1] < 5:
            continue
        d.columns = [str(c).strip() for c in d.columns]
        ren = {"日期": "date", "开盘": "open", "最高": "high", "最低": "low",
               "收盘": "close", "成交量": "volume", "成交额": "amount"}
        d = d.rename(columns=ren)
        need = {"date", "open", "high", "low", "close"}
        if not need.issubset(set(d.columns)):
            continue
        d["code"] = ("sh" if code6[0] == "6" else "sz") + code6
        d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        for c in ["open", "high", "low", "close", "volume", "amount"]:
            if c in d:
                d[c] = pd.to_numeric(d[c], errors="coerce")
            else:
                d[c] = 0.0
        frames.append(d[KEEP_COLS].dropna(subset=["date", "close"]))
    if not frames:
        raise RuntimeError(f"{root_dir} 下没有解析到有效的通达信日线 CSV")
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["code", "date"])
    df.to_parquet(DAILY_CACHE, index=False)
    return df


if __name__ == "__main__":
    fetch_all()
