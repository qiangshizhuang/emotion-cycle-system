# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置

生成方式（Windows 上执行）：
    pyinstaller build.spec --noconfirm

产物：
    dist/情绪周期系统/情绪周期系统.exe   ← 双击运行
"""
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# akshare 内部有大量动态导入，必须显式收集，否则打包后一抓数据就报 ModuleNotFoundError
hidden = []
for pkg in ("akshare", "curl_cffi", "jsonpath", "mini_racer", "py_mini_racer", "jsonpath_rw"):
    try:
        hidden += collect_submodules(pkg)
    except Exception:
        pass

hidden += [
    "pandas", "numpy", "pyarrow", "bs4", "lxml", "lxml.etree", "html5lib",
    "requests", "urllib3", "openpyxl", "xlrd", "tqdm", "tabulate", "decorator",
    "certifi", "charset_normalizer", "idna", "dateutil", "pytz", "six",
]

datas = []
for pkg in ("akshare",):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

# 排除与功能无关的大体积库，控制体积
excludes = [
    "matplotlib", "scipy", "sklearn", "notebook", "jupyter", "IPython",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "tkinter",
    "pytest", "sphinx", "docutils", "babel", "pygame", "cv2",
]

# 兼容不同 PyInstaller 版本：SPEC 变量在 6.x 由运行器注入，取不到就退回当前工作目录
try:
    _HERE = os.path.dirname(os.path.abspath(SPEC))  # noqa: F821
except NameError:
    _HERE = os.getcwd()

# 内置数据快照：首次运行秒级载入，免去 5223 只股票逐只下载的 6~8 分钟。
# 没有这个目录也能打包，只是用户首次运行时得在线全量下载。
_seed_dir = os.path.join(_HERE, "data_seed")
_seed_files = []
if os.path.isdir(_seed_dir):
    for fn in sorted(os.listdir(_seed_dir)):
        if fn.endswith((".parquet", ".csv")):
            datas.append((os.path.join(_seed_dir, fn), "data_seed"))
            _seed_files.append(fn)

icon_path = os.path.join(_HERE, "icon.ico")
if not os.path.exists(icon_path):
    icon_path = None

a = Analysis(
    ["app.py"],
    pathex=[_HERE],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

print(f"[build.spec] seed files: {len(_seed_files)} -> {_seed_files}")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="情绪周期系统",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # 保留控制台，抓数据时能看到进度
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="情绪周期系统",
)
