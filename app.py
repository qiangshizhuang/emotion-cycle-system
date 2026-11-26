#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股情绪周期系统 · 双击运行入口

双击 exe（或 python app.py）即：
  1. 增量更新数据（首次会自动全量下载）
  2. 计算情绪温度与阶段
  3. 生成 HTML 仪表盘并在浏览器中打开

高级用法（命令行）：
  app.exe --end 2024-09-30     复盘历史某天
  app.exe --no-update          不联网，用本地数据
  app.exe --local "D:/日线数据"  用通达信导出的 CSV
"""
import os
import sys
import time
import argparse
import traceback
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _setup_console():
    """Windows 控制台中文编码修正。"""
    if os.name == "nt":
        try:
            os.system("chcp 65001 >nul 2>&1")
        except Exception:
            pass
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _pause():
    """双击运行时窗口不要一闪而过。"""
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\n按回车键退出...")
    except Exception:
        pass


def _selftest():
    """
    启动自检：不联网、不下数据，只验证「这个 exe 拆包之后依赖是否齐全」。
    CI 里打包完成后会立刻跑一次，能在你下载之前就发现缺模块的问题。
    返回 0 表示健康。
    """
    import tempfile
    import runtime

    results = []

    def check(name, fn):
        try:
            detail = fn() or ""
            results.append((True, name, str(detail)))
        except Exception as e:
            results.append((False, name, f"{type(e).__name__}: {e}"))

    def _dirs():
        runtime.load_external_config()
        p = os.path.join(runtime.cache_dir(), ".write_test")
        with open(p, "w") as f:
            f.write("ok")
        os.remove(p)
        return f"cache={runtime.cache_dir()}"

    def _numpy_pandas():
        import numpy as np
        import pandas as pd
        return f"pandas {pd.__version__} / numpy {np.__version__}"

    def _parquet():
        import pandas as pd
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "t.parquet")
            df.to_parquet(p, index=False)
            back = pd.read_parquet(p)
        assert len(back) == 3
        import pyarrow
        return f"pyarrow {pyarrow.__version__}"

    def _akshare():
        import importlib
        import akshare as ak
        from data import akcompat

        # 走兼容层解析，测的就是程序运行时真正调用的那条路径。
        # akshare 在 1.20.46 改过接口名，写死名字会让自检本身变成误报。
        ver, got = akcompat.describe()
        for name in got.values():
            fn = getattr(ak, name)
            assert callable(fn), f"接口不可用：{name}"
            importlib.import_module(fn.__module__)  # 打包后最容易缺的是这些动态导入
        return f"akshare {ver} / {got['spot']}"

    def _core_logic():
        """用合成数据跑一遍核心链路，验证指标/打分/状态机没被裁坏。"""
        import numpy as np
        import pandas as pd
        from core import metrics, score, cycle

        rng = np.random.default_rng(0)
        dates = pd.bdate_range("2024-01-02", periods=90).strftime("%Y-%m-%d")
        codes = [f"sh{600000 + i}" for i in range(12)] + [f"sz{1 + i:06d}" for i in range(12)]
        rows = []
        for c in codes:
            px = 10.0
            for dt in dates:
                px *= 1 + rng.normal(0, 0.03)
                rows.append({
                    "date": dt, "code": c, "open": px, "high": px * 1.01,
                    "low": px * 0.99, "close": px, "volume": 100000, "amount": px * 100000,
                })
        raw = pd.DataFrame(rows)
        lst = pd.DataFrame({"code": codes, "name": ["T"] * len(codes), "is_st": [False] * len(codes)})
        flags = metrics.build_daily_flags(raw, lst)
        sent = metrics.daily_sentiment(flags)
        scored = score.compute_score(sent)
        done = cycle.detect_phase(scored)
        # 首日没有前收盘，会被剔除，所以是 N-1 个交易日
        assert len(done) == len(dates) - 1, f"交易日数量对不上：{len(done)}"
        # 分位数需要预热期（PCT_MIN_PERIODS），只校验预热结束后不能有空洞
        assert done["score"].tail(10).notna().all(), "温度在预热期后出现空值"
        assert done["phase_name"].tail(1).notna().all(), "阶段判定未生效"
        return f"{len(done)} 个交易日 / 涨停均值 {done['zt_count'].mean():.1f}"

    def _seed():
        """内置数据快照：这是首次运行免下载的关键，打包后必须存在。"""
        import pandas as pd
        import runtime
        seed = runtime.seed_dir()
        if seed:
            f = os.path.join(seed, "daily_all.parquet")
            assert os.path.exists(f), "快照目录存在但缺 daily_all.parquet"
            d = pd.read_parquet(f, columns=["date"])
            return f"{len(d):,} 行，覆盖至 {d['date'].max()}"
        if runtime.is_frozen():
            raise AssertionError("包内没有数据快照，用户首次运行要在线下载 6~8 分钟")
        return "源码模式，无快照（正常）"

    def _fast_api():
        """增量更新走的 K 线接口。函数内延迟导入，打包时最容易被漏掉。"""
        from data import sina_kline
        assert callable(sina_kline.fetch_recent), "sina_kline.fetch_recent 不可用"
        assert hasattr(sina_kline, "fetch_one"), "sina_kline.fetch_one 不可用"
        return "增量接口已打包"

    def _render():
        from output import charts
        svg = charts.line_chart(["2024-01-01", "2024-01-02"], [([1, 2], "#fff", "t", 2)])
        assert svg.startswith("<svg"), "图表渲染失败"
        import output.report  # noqa: F401
        return f"SVG {len(svg)} 字节"

    check("目录可写", _dirs)
    check("numpy / pandas", _numpy_pandas)
    check("parquet 读写", _parquet)
    check("内置数据快照", _seed)
    check("akshare 接口", _akshare)
    check("增量快速接口", _fast_api)
    check("核心计算链路", _core_logic)
    check("SVG 渲染", _render)

    print("\n" + "=" * 60)
    print("  启动自检")
    print("=" * 60)
    bad = 0
    for ok, name, detail in results:
        print(f"  [{'OK ' if ok else 'FAIL'}] {name:<16} {detail[:80]}")
        if not ok:
            bad += 1
    print("=" * 60)
    if bad:
        print(f"  {bad} 项失败：这个包在别人电脑上会跑不起来")
    else:
        print("  全部通过：依赖完整，可以直接分发")
    return 1 if bad else 0


def main():
    _setup_console()
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--end", default=None, help="数据截止日 YYYY-MM-DD")
    ap.add_argument("--no-update", action="store_true", help="不联网，用本地缓存")
    ap.add_argument("--local", default=None, help="本地通达信日线 CSV 目录")
    ap.add_argument("--full", action="store_true", help="强制全量重抓")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--selftest", action="store_true", help="只做启动自检，不联网不出报告")
    ap.add_argument("--update-only", action="store_true", help="只把数据补到最新，不出报告")
    ap.add_argument("--version", action="version", version="情绪周期系统 1.2")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    import runtime
    runtime.load_external_config()      # 允许 exe 同目录的 config.py 覆盖参数
    runtime.silence_noise()             # 压掉 py_mini_racer 的析构噪音

    import config
    from data import fetcher
    from core.pipeline import run
    from output import report

    print("=" * 60)
    print("  A股情绪周期系统")
    print("=" * 60)
    print(f"  程序目录：{runtime.app_dir()}")
    print(f"  数据目录：{runtime.cache_dir()}")
    print(f"  报告目录：{runtime.reports_dir()}")
    print()

    try:
        if args.local:
            print(f"[0/3] 导入本地通达信数据：{args.local}")
            df = fetcher.load_from_local_csv(args.local)
            print(f"      导入 {len(df):,} 行 / {df['code'].nunique()} 只股票\n")

        if args.full:
            print("[0/3] 强制全量重抓数据（会重新下载全部历史，约 6 分钟）...")
            fetcher.update(args.end, full=True)

        if args.update_only:
            print("[更新] 只补数据，不生成报告 ...")
            df = fetcher.update(args.end, budget=600)
            print(f"\n数据已更新至 {df['date'].max()}，共 {len(df):,} 行")
            print(f"缓存：{fetcher.DAILY_CACHE}")
            return

        # 有内置快照就不必干等下载；没有才走在线全量
        has_cache = os.path.exists(fetcher.DAILY_CACHE)
        seed = runtime.seed_dir()
        print("[1/3] 准备数据")
        if has_cache:
            pass
        elif seed and os.path.exists(os.path.join(seed, "daily_all.parquet")):
            print("  首次运行：从内置数据快照载入（本地复制，秒级完成）")
        elif not args.no_update:
            print("  首次运行：包内没有数据快照，需要在线下载全部沪深 A 股约 4 年日线")
            print("  约 5223 只、470 万行，预计 6~8 分钟，进度见下方进度条")
            print("  下载完会缓存，以后每次运行只补最近几个交易日\n")

        t0 = time.time()
        sent, stats, trans = run(start=None, end=args.end,
                                 auto_update=not args.no_update,
                                 budget=None if args.no_update else config.UPDATE_BUDGET)

        print("\n[3/3] 生成报告...")
        stamp = sent["date"].iloc[-1].replace("-", "")
        out = os.path.join(runtime.reports_dir(), f"情绪周期仪表盘_{stamp}.html")
        report.build_html(sent, stats, out, trans)

        last = sent.iloc[-1]
        adv = config.ADVICE[last["phase"]]
        print()
        print("=" * 60)
        print(f"  {last['date']}    阶段：{last['phase_name']}    温度：{last['score']:.0f}")
        print(f"  涨停 {int(last['zt_count'])} 家 / 跌停 {int(last['dt_count'])} 家 / "
              f"最高 {int(last['max_board'])} 板 / 昨涨停溢价 {last['prem']:+.1f}%")
        print(f"  建议仓位：{adv['position']}")
        print("=" * 60)
        print(f"\n报告：{out}")
        print(f"耗时：{time.time() - t0:.0f} 秒")

        if not args.no_browser:
            print("\n正在打开浏览器...")
            try:
                webbrowser.open("file:///" + out.replace("\\", "/"))
            except Exception:
                print("自动打开失败，请手动双击上面的 html 文件。")

    except KeyboardInterrupt:
        print("\n已取消。")
    except Exception:
        print("\n" + "!" * 60)
        print("运行出错，详细信息如下（可截图反馈）：")
        print("!" * 60)
        traceback.print_exc()
    finally:
        _pause()


if __name__ == "__main__":
    main()
