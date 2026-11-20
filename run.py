#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股情绪周期系统 · 命令行入口

用法示例
--------
python run.py                          # 更新数据 + 生成今日仪表盘
python run.py --no-update              # 不联网，直接用本地库出报告
python run.py --end 2024-09-30         # 复盘：还原 2024-09-30 当天的状态
python run.py --local "E:/桌面/日线数据"  # 用通达信导出的 CSV 作为数据源
python run.py --full                   # 强制全量重抓（首次安装用）
"""
import os
import sys
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config


def main():
    ap = argparse.ArgumentParser(description="A股情绪周期系统")
    ap.add_argument("--end", default=None, help="数据截止日 YYYY-MM-DD（用于历史复盘）")
    ap.add_argument("--start", default=None, help="历史数据起点，默认 config.DATA_START")
    ap.add_argument("--no-update", action="store_true", help="不联网，直接用本地缓存")
    ap.add_argument("--full", action="store_true", help="强制全量重抓")
    ap.add_argument("--local", default=None, help="本地通达信日线 CSV 目录")
    ap.add_argument("--out", default=None, help="报告输出路径")
    args = ap.parse_args()

    from data import fetcher
    from core.pipeline import run
    from output import report

    if args.local:
        print(f"从本地 CSV 导入：{args.local}")
        df = fetcher.load_from_local_csv(args.local)
        print(f"  导入 {len(df):,} 行 / {df['code'].nunique()} 只")

    if args.full:
        fetcher.update(args.start, args.end, full=True)

    s, st, tr = run(start=args.start, end=args.end, auto_update=not args.no_update)

    stamp = s["date"].iloc[-1].replace("-", "")
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "reports", f"情绪周期仪表盘_{stamp}.html")
    report.build_html(s, st, out, tr)

    last = s.iloc[-1]
    print("\n" + "=" * 56)
    print(f"  {last['date']}   阶段：{last['phase_name']}   温度：{last['score']:.0f}")
    print(f"  涨停 {int(last['zt_count'])} 家 / 跌停 {int(last['dt_count'])} 家 / "
          f"最高 {int(last['max_board'])} 板 / 昨涨停溢价 {last['prem']:+.1f}%")
    print(f"  建议仓位：{config.ADVICE[last['phase']]['position']}")
    print("=" * 56)
    print(f"\n报告已生成：{out}")


if __name__ == "__main__":
    main()
