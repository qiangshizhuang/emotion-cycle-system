# -*- coding: utf-8 -*-
"""
运行环境适配：源码运行 / PyInstaller 打包（exe）两种模式下的路径解析。

打包后的关键区别
- sys.frozen 为 True，__file__ 指向临时解压目录（onefile 模式下每次启动都变）
- 数据、报告、配置**绝不能**写到解压目录，否则退出即丢
- 统一写到 exe 所在目录，用户能看见、能备份、能改配置
"""
import os
import sys


def is_frozen():
    return getattr(sys, "frozen", False)


def app_dir():
    """可写目录：exe 所在目录（打包后）或项目根目录（源码运行）。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def res_dir():
    """只读资源目录：onefile 模式下是 _MEIPASS。"""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def cache_dir():
    p = os.path.join(app_dir(), "data", "cache")
    os.makedirs(p, exist_ok=True)
    return p


def reports_dir():
    p = os.path.join(app_dir(), "reports")
    os.makedirs(p, exist_ok=True)
    return p


def load_external_config():
    """
    优先加载 exe 同目录下的 config.py，让用户能在不改程序的前提下调参数。
    必须在 import config 之前调用。
    """
    ext = os.path.join(app_dir(), "config.py")
    if not os.path.exists(ext):
        return False
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("config", ext)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["config"] = mod
        spec.loader.exec_module(mod)
        return True
    except Exception:
        sys.modules.pop("config", None)
        return False
