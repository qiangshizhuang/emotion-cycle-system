# -*- coding: utf-8 -*-
"""主管线：数据 → 指标 → 打分 → 阶段 → 输出"""
import os
import sys
import time
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import runtime
from data import fetcher
from data import index_data
from core import metrics, score, cycle

OUT_DIR = runtime.reports_dir()


def run(start=None, end=None, verbose=True, auto_update=True):
    t0 = time.time()

    def log(m):
        if verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

    log("① 加载全市场日线 ...")
    daily = fetcher.load(start, end, auto_update=auto_update)
    sl = fetcher.get_stock_list()
    log(f"    {len(daily):,} 行 / {daily['code'].nunique()} 只")

    log("② 标注涨跌停 / 连板 ...")
    flags = metrics.build_daily_flags(daily, sl)

    log("③ 聚合每日情绪指标 ...")
    sent = metrics.daily_sentiment(flags)

    log("④ 合并指数 ...")
    idx = index_data.load_index("sh000001")
    sent = metrics.add_index(sent, idx)

    log("⑤ 情绪温度打分 ...")
    sent = score.compute_score(sent)

    log("⑥ 状态机识别阶段 ...")
    sent = cycle.detect_phase(sent)

    log("⑦ 阶段画像统计 ...")
    stats = cycle.phase_stats(sent)
    trans = cycle.transition_prob(sent)

    stamp = sent["date"].iloc[-1].replace("-", "")
    csv_daily = os.path.join(OUT_DIR, f"情绪周期_每日指标_{stamp}.csv")
    csv_stats = os.path.join(OUT_DIR, f"情绪周期_阶段画像_{stamp}.csv")
    csv_trans = os.path.join(OUT_DIR, f"情绪周期_阶段转移_{stamp}.csv")
    sent.to_csv(csv_daily, index=False, encoding="utf-8-sig")
    stats.to_csv(csv_stats, index=False, encoding="utf-8-sig")
    trans.to_csv(csv_trans, encoding="utf-8-sig")

    log(f"⑧ 输出：{csv_daily}")
    log(f"    {csv_stats}   总耗时 {time.time() - t0:.1f}s")

    # 清洗输出列
    keep = ["date", "phase", "phase_name", "phase_valid", "phase_seg", "phase_day_n", "phase_len",
            "score", "score_ema3", "score_ma5", "score_chg5",
            "s_limit_up", "s_seal_quality", "s_money_effect", "s_loss_effect", "s_breadth", "s_volume",
            "zt_count", "dt_count", "zb_count", "seal_rate", "max_board", "board2", "board3",
            "up_count", "down_count", "breadth", "prem", "prem_win", "prem_dt", "big_loss",
            "amount_yi", "amt_ratio", "eq_ret", "eq_index", "idx_close", "idx_pct",
            "zt_pct", "dt_pct", "bl_pct", "prem_pct", "promo_rate", "stock_n"]
    keep = [c for c in keep if c in sent.columns]
    return sent[keep].copy(), stats, trans


if __name__ == "__main__":
    s, st, tr = run()
    print(st.to_string(index=False))
