# -*- coding: utf-8 -*-
"""
重新生成内置数据快照（data_seed/）

发新版前跑一次，让包里的数据尽量新——用户下载后首次运行就不必补太多天。

    python tools/make_seed.py

做三件事：
  1. 把本地日线库更新到最新交易日
  2. 用 zstd 重压一遍写进 data_seed/（比默认压缩小 20%）
  3. 同步股票列表与指数缓存
"""
import os
import sys
import time
import shutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.chdir(HERE)

import pandas as pd                      # noqa: E402
from data import fetcher, index_data     # noqa: E402

SEED = os.path.join(HERE, "data_seed")


def main():
    os.makedirs(SEED, exist_ok=True)

    print("[1/3] 更新本地日线库 ...")
    t0 = time.time()
    df = fetcher.update()
    print(f"      {len(df):,} 行 / {df['code'].nunique()} 只，"
          f"截至 {df['date'].max()}，耗时 {time.time() - t0:.0f}s")

    print("[2/3] 写入快照 ...")
    dst = os.path.join(SEED, "daily_all.parquet")
    df.to_parquet(dst, index=False, compression="zstd", compression_level=9)
    print(f"      {dst}  {os.path.getsize(dst) / 1048576:.1f} MB")

    print("[3/3] 同步股票列表与指数 ...")
    for sym in index_data.INDEXES:
        try:
            index_data.fetch_index(sym)
        except Exception as e:
            print(f"      {sym} 抓取失败：{e}")
    for fn in ("stock_list.csv", "index_sh000001.parquet", "index_sz399006.parquet"):
        src = os.path.join(fetcher.CACHE_DIR, fn)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(SEED, fn))
            print(f"      {fn}")

    print("\n完成。提交前确认 data_seed/ 已在 git 里：")
    print("      git add data_seed && git commit -m \"更新内置数据\"")


if __name__ == "__main__":
    main()
