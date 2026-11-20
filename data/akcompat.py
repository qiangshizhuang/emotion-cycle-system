# -*- coding: utf-8 -*-
"""
akshare 接口兼容层

背景：akshare 在 1.20.46 起把新浪数据源的三个接口改了名，且不做向后兼容——

    旧名                        新名
    stock_zh_a_spot         →   stock_zh_a_spot_sina
    stock_zh_a_daily        →   stock_zh_a_hist_sina
    stock_zh_index_daily    →   index_zh_daily_sina

如果直接写死新名字，锁在旧版本的用户会挂；写死旧名字，装到新版的用户会挂。
所以这里统一按「新名优先、旧名兜底」解析，并把日期参数格式的差异一并抹平。

注意：新接口的 start_date 要求 YYYYMMDD（不带横线），旧接口两种都接受。
"""

SPOT_CANDIDATES = ("stock_zh_a_spot_sina", "stock_zh_a_spot")
DAILY_CANDIDATES = ("stock_zh_a_hist_sina", "stock_zh_a_daily")
INDEX_CANDIDATES = ("index_zh_daily_sina", "stock_zh_index_daily")


def _resolve(names):
    """按候选顺序返回第一个存在的接口，同时返回它实际的名字。"""
    import akshare as ak
    for n in names:
        fn = getattr(ak, n, None)
        if callable(fn):
            return n, fn
    raise AttributeError(f"当前 akshare 里找不到这些接口：{names}，请升级或降级 akshare")


def _ymd(s):
    """把 2024-01-01 变成 20240101；已经是紧凑格式就原样返回。"""
    return str(s).replace("-", "")


def spot():
    """全市场实时快照（含代码、名称，用于取股票池与 ST 标记）。"""
    return _resolve(SPOT_CANDIDATES)[1]()


def daily(code, start, end, adjust=""):
    """单只股票日线。code 形如 sh600000。"""
    name, fn = _resolve(DAILY_CANDIDATES)
    if name == "stock_zh_a_hist_sina":
        return fn(symbol=code, period="daily",
                  start_date=_ymd(start), end_date=_ymd(end), adjust=adjust)
    return fn(symbol=code, start_date=start, end_date=end, adjust=adjust)


def index_daily(symbol="sh000001"):
    """指数日线。"""
    return _resolve(INDEX_CANDIDATES)[1](symbol=symbol)


def describe():
    """自检用：返回当前解析到的接口名，方便判断跑在哪个版本上。"""
    import akshare as ak
    got = {
        "spot": _resolve(SPOT_CANDIDATES)[0],
        "daily": _resolve(DAILY_CANDIDATES)[0],
        "index": _resolve(INDEX_CANDIDATES)[0],
    }
    return ak.__version__, got
