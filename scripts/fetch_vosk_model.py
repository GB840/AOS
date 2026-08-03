"""下载 Vosk 中文离线语音模型（母纲原则 7 落地脚手架）。

为什么要这个脚本：官方站 alphacephei.com 在国内经常超时，一句
「请自行下载模型」就是把老百姓挡在门外。这里做多源回退 + 断点续传，
让「断网前先把模型拿到手」这件事真能完成。

用法：
    python scripts/fetch_vosk_model.py                 # 默认中文小模型 (~42MB)
    python scripts/fetch_vosk_model.py --large         # 中文大模型 (~1.3GB)
    python scripts/fetch_vosk_model.py --dir D:/models # 指定目录

下完之后 `VoskSTT().available` 会自动发现它（无需设环境变量）。
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

SMALL_CN = "vosk-model-small-cn-0.22"
LARGE_CN = "vosk-model-cn-0.22"

# 多源：国内镜像优先，官方兜底。任一成功即止。
# 实测（2026-08-04，中国大陆）：hf-mirror 41.9MB / 5 秒；
# 官方 alphacephei.com 12 分钟只下到 4MB。所以镜像必须排前面。
_HF_MIRROR_REPOS = {
    # 社区搬运仓（已实测可用）；zip 内顶层目录名为 vosk-model-small-cn
    SMALL_CN: ("guloooovoooo/vosk-model-small-cn", "vosk-model-small-cn.zip",
               "vosk-model-small-cn"),
}


def sources_for(name: str) -> list:
    urls = []
    hit = _HF_MIRROR_REPOS.get(name)
    if hit:
        repo, fname, _ = hit
        urls.append(f"https://hf-mirror.com/{repo}/resolve/main/{fname}")
    urls += [
        f"https://hf-mirror.com/csukuangfj/vosk-models/resolve/main/{name}.zip",
        f"https://hf-mirror.com/alphacep/{name}/resolve/main/{name}.zip",
        # 官方源（境外，权威但国内常超时；靠断点续传硬啃）
        f"https://alphacephei.com/vosk/models/{name}.zip",
    ]
    return urls


def expected_dirs(name: str) -> list:
    """该模型解压后可能的顶层目录名（镜像搬运包名字未必带版本号）。

    诚实纪律：镜像包若无版本佐证，**不给它改名冒充某版本**，按原名认。
    """
    dirs = [name]
    hit = _HF_MIRROR_REPOS.get(name)
    if hit and hit[2] not in dirs:
        dirs.append(hit[2])
    return dirs


def default_dir() -> str:
    return os.environ.get("AOS_VOSK_MODEL_DIR") or os.path.expanduser(
        "~/.cache/vosk-models")


def _download(url: str, dest_zip: str, timeout: int = 60,
              retries: int = 3) -> bool:
    """分块下载 + Range 断点续传。成功返回 True。"""
    for attempt in range(1, retries + 1):
        have = os.path.getsize(dest_zip) if os.path.exists(dest_zip) else 0
        req = urllib.request.Request(url, headers={"User-Agent": "aos-fetch/1.0"})
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                total = resp.headers.get("Content-Length")
                total = (int(total) + have) if total else 0
                mode = "ab" if (have and resp.status == 206) else "wb"
                if mode == "wb":
                    have = 0
                got = have
                last = time.time()
                with open(dest_zip, mode) as f:
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        if time.time() - last > 3:
                            pct = f"{got * 100 // total}%" if total else "?"
                            print(f"  ... {got / 1048576:.1f}MB {pct}", flush=True)
                            last = time.time()
            if os.path.getsize(dest_zip) > 1024:
                return True
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                OSError) as exc:
            code = getattr(exc, "code", None)
            if code in (403, 404):
                print(f"  源不可用({code})，换下一个", flush=True)
                return False
            print(f"  第 {attempt}/{retries} 次失败: {exc}；续传重试", flush=True)
            time.sleep(2)
    return False


def fetch(name: str, base: str) -> str:
    os.makedirs(base, exist_ok=True)
    wanted = expected_dirs(name)
    for cand in wanted:
        p = os.path.join(base, cand)
        if os.path.isdir(p):
            print(f"[已存在] {p}")
            return p

    dest_zip = os.path.join(base, name + ".zip.part")
    for url in sources_for(name):
        print(f"[尝试] {url}", flush=True)
        if _download(url, dest_zip):
            try:
                with zipfile.ZipFile(dest_zip) as zf:
                    # __MACOSX 是 macOS 压缩残渣，解出来是垃圾，跳过
                    for n in zf.namelist():
                        if not n.startswith("__MACOSX"):
                            zf.extract(n, base)
            except zipfile.BadZipFile:
                print("  下载内容不是有效 zip（可能是错误页），换下一个源")
                os.remove(dest_zip)
                continue
            os.remove(dest_zip)
            for cand in wanted:
                p = os.path.join(base, cand)
                if os.path.isdir(p):
                    print(f"[完成] {p}")
                    return p
            print("  解压后未见预期目录，换下一个源")
    raise SystemExit(
        "所有源都失败。手动方案：浏览器打开 "
        f"https://alphacephei.com/vosk/models/{name}.zip 下载后解压到 {base}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--large", action="store_true", help="下载 1.3GB 高精度大模型")
    ap.add_argument("--dir", default=None, help="模型存放目录")
    args = ap.parse_args()
    name = LARGE_CN if args.large else SMALL_CN
    base = args.dir or default_dir()
    path = fetch(name, base)
    print("\n验证：")
    print("  python -c \"import sys; sys.path.insert(0,'src'); "
          "from core.fabric.adapters.vosk_backend import VoskSTT; "
          "print(VoskSTT().health_detail())\"")
    print(f"  模型路径: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
