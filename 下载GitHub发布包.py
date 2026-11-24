#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 发布包下载器

为什么需要它：私有仓库的 Release 附件，浏览器未登录时一律返回 404（GitHub 故意不返回 403，
免得别人探测仓库是否存在）。这个工具用令牌走 API 取附件，不需要浏览器登录状态。

用法：
    python 下载GitHub发布包.py                          # 下载默认仓库的最新版
    python 下载GitHub发布包.py 用户名/仓库名              # 指定仓库
    python 下载GitHub发布包.py 用户名/仓库名 v1.0         # 指定标签
    python 下载GitHub发布包.py 用户名/仓库名 v1.0 ghp_xxx  # 直接给令牌

令牌优先级：命令行参数 > 环境变量 GITHUB_TOKEN > 同目录 token.txt > 交互输入

Windows 用户直接双击 下载发布包.bat 即可。
"""
import os
import sys
import time
import getpass

DEFAULT_REPO = "qiangshizhuang/emotion-cycle-system"
API = "https://api.github.com"


def _http():
    try:
        import requests
        return requests
    except ImportError:
        sys.exit("缺少 requests 库，请先执行：pip install requests")


def _load_token(arg_token=None):
    if arg_token:
        return arg_token.strip()
    env = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env:
        return env.strip()
    here = os.path.dirname(os.path.abspath(__file__))
    f = os.path.join(here, "token.txt")
    if os.path.exists(f):
        with open(f, encoding="utf-8") as fh:
            t = fh.read().strip()
        if t:
            print(f"已读取 token.txt（{t[:4]}****）")
            return t
    print("需要 GitHub 令牌（仓库私有时必须）。")
    print("获取：https://github.com/settings/tokens → Generate new token (classic) → 勾选 repo")
    print("也可以把它保存成同目录下的 token.txt，以后就不用每次输入。")
    return getpass.getpass("粘贴令牌后回车（输入不显示）：").strip()


def _api_get(session, url, token, **kw):
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return session.get(url, headers=headers, timeout=30, **kw)


def list_assets(session, repo, tag, token):
    """返回 (release 信息, 附件列表)。tag 为空则取 latest。"""
    url = f"{API}/repos/{repo}/releases/tags/{tag}" if tag else f"{API}/repos/{repo}/releases/latest"
    r = _api_get(session, url, token)
    if r.status_code == 404:
        print(f"\n取不到发布：{url}")
        print("三种可能：")
        print("  1) 仓库私有且令牌无效/没权限 → 换一个带 repo 权限的令牌")
        print("  2) 标签写错了 → 先去 Releases 页面看准确的版本号")
        print("  3) 仓库名拼错 → 格式是 用户名/仓库名")
        sys.exit(2)
    r.raise_for_status()
    rel = r.json()
    return rel, rel.get("assets", [])


def download(session, repo, asset, token, out_dir):
    name = asset["name"]
    total = asset["size"]
    dest = os.path.join(out_dir, name)
    part = dest + ".part"

    done = os.path.getsize(part) if os.path.exists(part) else 0
    if os.path.exists(dest) and os.path.getsize(dest) == total:
        print(f"已存在且大小一致，跳过：{name}")
        return dest

    headers = {"Accept": "application/octet-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if done:
        headers["Range"] = f"bytes={done}-"
        print(f"从 {done / 1048576:.1f}MB 处续传")

    url = f"{API}/repos/{repo}/releases/assets/{asset['id']}"
    t0 = time.time()
    with session.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True) as r:
        r.raise_for_status()
        mode = "ab" if done else "wb"
        with open(part, mode) as f:
            last = 0.0
            for chunk in r.iter_content(chunk_size=262144):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                now = time.time()
                if now - last > 0.3:
                    last = now
                    pct = done / total * 100 if total else 0
                    spd = done / max(now - t0, 0.001) / 1048576
                    bar = "█" * int(pct / 4) + "·" * (25 - int(pct / 4))
                    sys.stdout.write(f"\r  {bar} {pct:5.1f}%  {done / 1048576:6.1f}/{total / 1048576:.1f}MB  {spd:5.1f}MB/s")
                    sys.stdout.flush()

    if total and os.path.getsize(part) != total:
        sys.exit(f"\n下载不完整：{os.path.getsize(part)} != {total}，重新运行会接着下")
    os.replace(part, dest)
    print(f"\n完成：{dest}（{os.path.getsize(dest) / 1048576:.1f}MB，{time.time() - t0:.0f} 秒）")
    return dest


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPO
    tag = sys.argv[2] if len(sys.argv) > 2 else ""
    arg_token = sys.argv[3] if len(sys.argv) > 3 else None

    token = _load_token(arg_token)
    requests = _http()
    s = requests.Session()
    here = os.path.dirname(os.path.abspath(__file__))

    print(f"仓库：{repo}")
    print(f"版本：{tag or '最新'}")
    rel, assets = list_assets(s, repo, tag, token)
    print(f"发布标题：{rel.get('name')}    附件 {len(assets)} 个\n")
    if not assets:
        sys.exit("这个发布没有附件。")

    for a in assets:
        print(f"- {a['name']}  {a['size'] / 1048576:.1f}MB")
    print()

    for a in assets:
        download(s, repo, a, token, here)

    print("\n全部完成。解压 zip 后双击 exe 即可。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已中断，重新运行会从断点续传。")
