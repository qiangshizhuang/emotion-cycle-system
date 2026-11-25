# -*- coding: utf-8 -*-
"""
数据层：全 A 股日线抓取（新浪源，不复权）
- 支持多线程并发 + 分片落盘 + 断点续传
- 也可切换为读取本地通达信导出 CSV（见 load_from_local_csv）
"""
import os
import sys
import json
import time
import glob
import random
import shutil
import socket
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import runtime

CACHE_DIR = runtime.cache_dir()

# 兜底超时：requests 若不设超时，单只请求可以无限挂着，
# 线程池里的 as_completed 就会一直等，表现出来就是「卡住不动」。
socket.setdefaulttimeout(20)

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

    from data import akcompat
    spot = akcompat.spot()
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


def _fetch_one(code, start, end, retries=1):
    from data import akcompat
    for i in range(retries):
        try:
            d = akcompat.daily(code, start, end, adjust="")
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
            time.sleep(0.4 + random.random() * 0.4)
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


def _trading_days_between(start, end):
    """借指数日历枚举 [start, end] 之间的交易日；取不到日历就退回自然日估算。"""
    try:
        from data import index_data
        idx = index_data.load_index("sh000001")
        days = [d for d in idx["date"].tolist() if start <= d <= end]
        if days:
            return sorted(days)
    except Exception:
        pass
    return [start]


def _fmt_sec(sec):
    sec = int(max(sec, 0))
    if sec < 60:
        return f"{sec} 秒"
    return f"{sec // 60} 分 {sec % 60:02d} 秒"


class _Progress:
    """
    单行刷新的抓取进度。

    之前没有进度输出，屏幕停在「全量抓取 5223 只」就一动不动，
    看起来和卡死没区别——其实后台一直在跑。这里补上百分比、速率和剩余时间。
    """
    BAR = 22

    def __init__(self, total, label="下载"):
        self.total = max(total, 1)
        self.label = label
        self.done = 0
        self.ok = 0
        self.t0 = time.time()
        self.tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        self._last = 0.0

    def tick(self, ok=True):
        self.done += 1
        if ok:
            self.ok += 1
        now = time.time()
        if self.done < self.total and now - self._last < 1.0:
            return
        self._last = now
        elapsed = max(now - self.t0, 0.001)
        rate = self.done / elapsed
        left = (self.total - self.done) / max(rate, 0.01)
        pct = self.done / self.total * 100
        filled = int(self.BAR * self.done / self.total)
        bar = "█" * filled + "─" * (self.BAR - filled)
        line = (f"  {self.label} {bar} {pct:5.1f}%  {self.done}/{self.total}  "
                f"{rate:.0f} 只/秒  剩余 {_fmt_sec(left)}")
        if self.tty:
            sys.stdout.write("\r" + line + "   ")
            sys.stdout.flush()
            if self.done >= self.total:
                sys.stdout.write("\n")
                sys.stdout.flush()
        elif self.done >= self.total or self.done % 1000 == 0:
            print(line.strip(), flush=True)

    def close(self):
        if self.tty and self.done < self.total:
            sys.stdout.write("\n")
            sys.stdout.flush()


def _install_seed():
    """
    把包内自带的日线快照拷进数据目录，返回是否成功。

    这是「双击就出报告」的前提：新浪接口只能逐只股票抓，5223 只无论怎么调并发
    都要好几分钟，而且并发一高就被限流（实测 8 并发 68ms/只，64 并发反而 123ms/只）。
    """
    seed = runtime.seed_dir()
    if not seed:
        return False
    src = os.path.join(seed, "daily_all.parquet")
    if not os.path.exists(src):
        return False
    try:
        shutil.copyfile(src, DAILY_CACHE)
        for fn in ("stock_list.csv", "index_sh000001.parquet", "index_sz399006.parquet"):
            sp = os.path.join(seed, fn)
            if os.path.exists(sp):
                shutil.copyfile(sp, os.path.join(CACHE_DIR, fn))
        d = pd.read_parquet(DAILY_CACHE)
        print(f"  已载入内置数据：{len(d):,} 行 / {d['code'].nunique()} 只，"
              f"覆盖至 {d['date'].max()}")
        print("  （无需下载历史数据，只补最近几个交易日）")
        return True
    except Exception as e:
        print(f"  内置数据载入失败（{type(e).__name__}），改为在线下载")
        return False


def _fetch_range(codes, start, end, workers=8, logf=None, label="下载", budget=None):
    """
    并发抓取指定区间，返回长表。

    两级策略：第一轮按设定并发跑，失败的股票降并发补抓一轮。
    新浪对高频请求会临时限流，一轮全失败的情况真实存在——补抓能把大部分捞回来，
    比当场重试更快（当场重试会让慢请求堵住整个线程池）。

    budget 为时间预算（秒），超时就带着已有数据返回，不让网络问题拖死整个程序。
    """
    rows, fail = [], 0
    bad = []
    t0 = time.time()
    timed_out = False

    def _round(batch, nworkers, tag):
        nonlocal fail, timed_out
        if not batch:
            return
        prog = _Progress(len(batch), tag)
        ex = ThreadPoolExecutor(max_workers=nworkers)
        try:
            futs = {ex.submit(_fetch_one, c, start, end): c for c in batch}
            for f in as_completed(futs):
                if budget and (time.time() - t0) > budget:
                    timed_out = True
                    break
                c = futs[f]
                try:
                    r = f.result()
                except Exception:
                    r = None
                if r is None or len(r) == 0:
                    fail += 1
                    bad.append(c)
                else:
                    rows.append(r)
                prog.tick(r is not None and len(r) > 0)
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
            prog.close()

    _round(codes, workers, label)

    # 补抓：只有没超时、且有失败时才做
    if bad and not timed_out:
        retry_list, bad = bad, []
        fail = 0
        # 失败多说明在限流，降并发给它喘息
        w2 = max(2, workers // 2) if len(retry_list) > len(codes) * 0.2 else workers
        _round(retry_list, w2, "补抓")

    if timed_out:
        print(f"\n  已达时间预算 {_fmt_sec(budget)}，先用现有数据出报告"
              f"（已取 {len(rows)} 只，缺的下次自动补）")
    if logf:
        _log(f"  {label} {start}~{end}：成功 {len(rows)} 只，失败 {len(bad)} 只", logf)

    got = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=KEEP_COLS)
    if bad and logf:
        _log(f"  仍未取到 {len(bad)} 只（多为停牌或无数据）", logf)
    return got


def update(start=None, end=None, workers=None, full=False, budget=None):
    """
    更新本地日线库（cache/daily_all.parquet）。

    三种情形自动分流：
      1. 库不存在 + 包内带快照 → 秒级复制，随后只补最后几个交易日
      2. 库不存在 + 无快照     → 在线全量下载（约 6 分钟，带进度条）
      3. 库已存在              → 只补增量

    budget：增量阶段的时间预算（秒）。超额就带着已有数据继续出报告，
    避免网络抽风时整个程序停在「全量抓取」那一行不动。
    """
    start = start or config.DATA_START
    end = end or time.strftime("%Y-%m-%d")
    workers = workers or config.FETCH_WORKERS
    logf = os.path.join(CACHE_DIR, "update.log")

    if full or not os.path.exists(DAILY_CACHE):
        # 先试内置快照，能省掉几分钟下载
        seeded = False if full else _install_seed()
        if not seeded:
            lst = get_stock_list(use_cache=False)
            codes = lst["code"].tolist()
            _log(f"全量抓取 {start} ~ {end}，股票 {len(codes)} 只，并发 {workers}", logf)
            df = _fetch_range(codes, start, end, workers, logf, label="全量下载", budget=budget)
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

    from data import snapshot

    lst = get_stock_list(use_cache=True)
    codes = lst["code"].tolist()
    nxt = (pd.Timestamp(last) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    gap_days = (pd.Timestamp(end) - pd.Timestamp(last)).days

    print(f"  库内数据截至 {last}，需补 {nxt} ~ {end}")
    _log(f"增量抓取 {nxt} ~ {end}（库内已有至 {last}），股票 {len(codes)} 只", logf)

    # 缺口恰好只有一个交易日时，走批量快照：一次请求 500 只，几秒钟完事。
    # 这是每天收盘后运行的最高频路径——逐只抓要 5223 次请求，差了几百倍。
    new = pd.DataFrame(columns=KEEP_COLS)
    missing_days = _trading_days_between(nxt, end)
    if len(missing_days) == 1:
        target = missing_days[0]
        print(f"  走批量快照接口（缺口仅 {target} 一天，通常几秒钟）")
        new = snapshot.fetch_day(codes, expect_date=target)
        if len(new):
            _log(f"批量快照：{len(new)} 只 / {target}", logf)
        else:
            print("  快照接口没取到该日数据，改用逐只抓取")

    if len(new) == 0:
        label = f"补 {nxt} 起 {gap_days} 天" if gap_days < 40 else "补增量"
        new = _fetch_range(codes, nxt, end, workers, logf, label=label, budget=budget)
    if len(new) == 0:
        _log("无新增数据（可能非交易日或网络异常），沿用现有缓存", logf)
        return old
    df = pd.concat([old, new], ignore_index=True).drop_duplicates(["code", "date"])
    df = df.sort_values(["code", "date"])
    df.to_parquet(DAILY_CACHE, index=False)
    _log(f"完成：新增 {len(df) - len(old):,} 行，总计 {len(df):,} 行，最新 {df['date'].max()}", logf)
    return df


def load(start=None, end=None, auto_update=True, budget=None):
    """统一读取入口：优先用本地库，必要时增量更新。"""
    start = start or config.DATA_START
    end = end or time.strftime("%Y-%m-%d")
    if auto_update:
        df = update(start, end, budget=budget)
    elif os.path.exists(DAILY_CACHE):
        df = pd.read_parquet(DAILY_CACHE)
    elif _install_seed():
        # 离线模式且没有缓存：用内置快照，这是 exe 首次运行的常见路径
        df = pd.read_parquet(DAILY_CACHE)
    else:
        raise RuntimeError(
            "本地没有数据，包内也没有内置快照。请去掉 --no-update 联网运行一次。"
        )
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
