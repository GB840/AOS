"""Scroll-World 国产版 —— 滚动着陆页「scrub-engine」构建器（调 AOS media-gen）。

替代 oso95/scroll-world 绑定的国外链路（Higgsfield 付费 + GPT Image 2 + Seedance），
改用 AOS FabricHub 的 media-gen 能力（国产智谱 CogView-4 文生图 + CogVideoX 文生视频）。
落实用户指令：「Scroll-World 这个用国产的做 因为他绑定的国外的模型」。

产物：一个自包含的滚动着陆页 index.html
- sticky 舞台（height:100vh）钉在视口
- 下方 track（height:N*100vh）提供滚动行程
- 滚动进度 p∈[0,1] 映射到场景索引 i + 局部进度 lp
- 场景间交叉淡入 + 视差 + 字幕位移
- 若场景带视频：video.currentTime 随滚动 scrub（签名效果）

两种模式：
- 真实模式：经 FabricHub.invoke_engine("media-gen", ...) 直打国产智谱出图/视频（钉死 media-gen，避免 route() 按档位误选 agnes 等外部引擎），下载到 assets/
- --dry-run：本地生成渐变占位 SVG，零网络零 key，用于离线验证 scrub 引擎

用法：
    # 离线验证（无需 key/网络）
    python examples/scroll_world_demo.py --dry-run --theme "赛博朋克城市" --scenes 4

    # 真机（需 .env 配 ZHIPU_API_KEY）
    python examples/scroll_world_demo.py --theme "国风山水" --scenes 5 --out out/landing

    # 多视频混排：左右分屏 / 2x2 网格
    python examples/scroll_world_demo.py --theme "未来都市" --scenes 4 --video --layout split
    python examples/scroll_world_demo.py --theme "未来都市" --scenes 3 --video --layout grid

    # 显式指定配色（否则按 --theme 关键词自动匹配）
    python examples/scroll_world_demo.py --theme "未来都市" --palette cyber

    # 用自定义场景（显式 prompt + 可选 video）
    python examples/scroll_world_demo.py --scenes-file scenes.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

# ---- 让示例能 import AOS 内核（不依赖安装） ----
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

CAP_IMAGE = "media.image"
CAP_VIDEO = "media.video"

DEFAULT_IMAGE_SIZE = "1024x1024"
DEFAULT_VIDEO_SIZE = "1280x720"

# ---- 配色主题（按 --theme 关键词自动匹配，或 --palette 显式指定） ----
PALETTES = {
    "cyber":   {"label": "赛博朋克", "grad_a": "#00f0ff", "grad_b": "#ff00e5",
                "overlay": "rgba(8,2,24,.55)", "accent": "#00f0ff",
                "font": "'Courier New', 'PingFang SC', monospace"},
    "guofeng": {"label": "国风", "grad_a": "#c0392b", "grad_b": "#e8b647",
                "overlay": "rgba(30,12,6,.5)", "accent": "#e8b647",
                "font": "'STKaiti','KaiTi','PingFang SC', serif"},
    "future":  {"label": "未来都市", "grad_a": "#4facfe", "grad_b": "#00f2fe",
                "overlay": "rgba(4,12,30,.5)", "accent": "#7fe7ff",
                "font": "'PingFang SC','Microsoft YaHei', sans-serif"},
    "nature":  {"label": "自然", "grad_a": "#11998e", "grad_b": "#38ef7d",
                "overlay": "rgba(4,20,10,.5)", "accent": "#7dffb0",
                "font": "'PingFang SC', sans-serif"},
    "noir":    {"label": "暗夜", "grad_a": "#434343", "grad_b": "#bdbdbd",
                "overlay": "rgba(0,0,0,.62)", "accent": "#e0e0e0",
                "font": "'PingFang SC', serif"},
    "sunset":  {"label": "落日", "grad_a": "#ff5f6d", "grad_b": "#ffc371",
                "overlay": "rgba(30,10,4,.5)", "accent": "#ffd28a",
                "font": "'PingFang SC', sans-serif"},
}
# 主题关键词 -> 调色板（不区分大小写包含匹配）
THEME_KEYWORDS = {
    "赛博": "cyber", "cyber": "cyber", "霓虹": "cyber", "机甲": "cyber",
    "国风": "guofeng", "古风": "guofeng", "山水": "guofeng", "水墨": "guofeng",
    "未来": "future", "都市": "future", "科技": "future", "城市": "future",
    "自然": "nature", "森林": "nature", "海": "nature", "风景": "nature",
    "夜": "noir", "暗": "noir", "黑": "noir",
    "落日": "sunset", "黄昏": "sunset", "晚霞": "sunset",
}


def pick_palette(theme: str, override: str | None = None) -> dict:
    """按主题关键词自动选调色板；--palette 可强制覆盖；都无命中用 future。"""
    if override and override in PALETTES:
        return PALETTES[override]
    t = (theme or "").lower()
    for kw, key in THEME_KEYWORDS.items():
        if kw.lower() in t:
            return PALETTES[key]
    return PALETTES["future"]


def _load_dotenv(path: str) -> None:
    """极简 .env 加载（仅注入本构建器需要的 key），不依赖 python-dotenv。"""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def build_scenes(theme: str, n: int) -> list[dict]:
    """从主题自动派生 N 个场景（标题/字幕/图 prompt/视频 prompt）。"""
    tones = [
        "开场全景，宏大辽阔",
        "中景推进，细节渐显",
        "特写聚焦，情绪拉满",
        "转折对比，张力迸发",
        "高潮收束，余韵悠长",
        "尾声回响，留白深远",
    ]
    scenes = []
    for i in range(n):
        tone = tones[i % len(tones)]
        img_prompt = (
            f"{theme}。{tone}。电影级构图，光影层次丰富，"
            f"高细节，8k，超写实摄影感，第{i+1}幕。"
        )
        vid_prompt = (
            f"Cinematic slow-motion shot of {theme}, {tone}, "
            f"smooth camera move, high detail, scene {i+1}."
        )
        scenes.append({
            "title": f"{theme} · 第{i+1}幕",
            "caption": f"{tone}。",
            "image_prompt": img_prompt,
            "video_prompt": vid_prompt,
            "video": False,  # 默认只出图；可在 scenes-file 里逐场景开
        })
    return scenes


def load_scenes(args) -> list[dict]:
    if args.scenes_file:
        with open(args.scenes_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兼容 [{"title":..., "image_prompt":...}] 或 {"theme":...,"scenes":[...]}
        if isinstance(data, dict) and "scenes" in data:
            return data["scenes"]
        return data
    return build_scenes(args.theme or "未来城市", max(1, args.scenes))


def _extract_url(data, is_video: bool):
    """从适配器返回里兼容提取资产 URL（兼容 media-gen 的 data.url 及其他后端形状）。"""
    if not isinstance(data, dict):
        return None
    for key in ("url", "image_url", "video_url"):
        if data.get(key):
            return data[key]
    nested = data.get("data")
    if isinstance(nested, list) and nested and isinstance(nested[0], dict):
        item = nested[0]
        return item.get("url") or item.get("image_url") or item.get("video_url")
    return None


def gen_asset(hub, capability: str, payload: dict, engine: str = "media-gen") -> str:
    """经 FabricHub 直打 media-gen（国产智谱），返回资产 URL 字符串。

    钉死 engine=media-gen，避免 route() 按档位误选 agnes 等外部引擎
    （其返回结构无 url 字段会致 KeyError）。缺 key / 失败如实抛错。
    """
    if hub is None:
        raise RuntimeError("dry-run 模式不会调用 gen_asset")
    res = hub.invoke_engine(engine, capability, payload)
    if not res.ok:
        raise RuntimeError(f"{capability} 生成失败({engine}): {res.error}")
    url = _extract_url(res.data, is_video=(capability == CAP_VIDEO))
    if not url:
        raise RuntimeError(f"{capability} 返回成功但无 url({engine}): {res.data}")
    return url


def _asset_ext(url: str, default: str = "png") -> str:
    for ext in ("png", "jpg", "jpeg", "webp", "mp4"):
        if url.lower().endswith(f".{ext}"):
            return ext if ext != "jpeg" else "jpg"
    return default


def download(url: str, dest: str, timeout: int = 60) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "AOS-scroll-world/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    with open(dest, "wb") as f:
        f.write(data)


def _placeholder_svg(path: str, idx: int, title: str) -> None:
    """dry-run：生成本地渐变占位 SVG，零网络。"""
    hue = (idx * 47) % 360
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="hsl({hue},70%,45%)"/>'
        f'<stop offset="100%" stop-color="hsl({(hue+60)%360},70%,25%)"/>'
        f'</linearGradient></defs>'
        f'<rect width="1280" height="720" fill="url(#g)"/>'
        f'<text x="640" y="360" fill="#fff" font-size="48" '
        f'text-anchor="middle" font-family="sans-serif">{title}</text>'
        f'<text x="640" y="420" fill="#fff" font-size="24" '
        f'text-anchor="middle" font-family="sans-serif">占位图 (dry-run)</text>'
        f'</svg>'
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


LAYOUT_VIDEO_COUNT = {"full": 1, "split": 2, "grid": 4}


def generate_assets(hub, scenes: list[dict], out_dir: str,
                    dry_run: bool, with_video: bool, layout: str = "full") -> list[dict]:
    """逐场景出图（/视频混排），落盘到 out_dir/assets，返回带本地路径的场景。

    layout 控制每幕视频路数：full=1（整屏）、split=2（左右）、grid=4（2x2）。
    无论几路视频，共用当幕一张海报图（image）作 poster，控制智谱 API 成本。
    """
    assets_dir = os.path.join(out_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    rendered = []
    n = len(scenes)
    vid_count = LAYOUT_VIDEO_COUNT.get(layout, 1)
    fails = 0
    for i, sc in enumerate(scenes):
        rel_img = f"assets/scene_{i+1}.png"
        img_path = os.path.join(out_dir, rel_img)
        if dry_run:
            _placeholder_svg(img_path, i, sc.get("title", f"Scene {i+1}"))
        else:
            try:
                print(f"[图] 场景 {i+1}/{n}: {sc['image_prompt'][:34]}...")
                url = gen_asset(hub, CAP_IMAGE, {
                    "mode": "image",
                    "prompt": sc["image_prompt"],
                    "size": DEFAULT_IMAGE_SIZE,
                })
                ext = _asset_ext(url)
                rel_img = f"assets/scene_{i+1}.{ext}"
                img_path = os.path.join(out_dir, rel_img)
                download(url, img_path)
                print(f"     -> {rel_img}")
            except Exception as e:
                fails += 1
                print(f"     ⚠️ 出图失败: {e}（用占位图续跑）")
                _placeholder_svg(img_path, i,
                                 (sc.get("title") or f"Scene {i+1}") + " · 出图失败")

        videos = []
        want_video = (not dry_run) and (with_video or sc.get("video"))
        if want_video:
            for vj in range(vid_count):
                suffix = f" 视角{vj+1}" if vid_count > 1 else ""
                try:
                    print(f"[视频 {vj+1}/{vid_count}] 场景 {i+1}/{n}: "
                          f"{sc['video_prompt'][:28]}{suffix}...")
                    vurl = gen_asset(hub, CAP_VIDEO, {
                        "mode": "video",
                        "prompt": sc["video_prompt"] + suffix,
                        "size": DEFAULT_VIDEO_SIZE,
                        "quality": "speed",
                        "duration": 5,
                        "with_audio": False,
                        "poll_timeout": 240,
                    })
                    rel_vid = f"assets/scene_{i+1}_v{vj+1}.mp4"
                    download(vurl, os.path.join(out_dir, rel_vid))
                    print(f"     -> {rel_vid}")
                    videos.append(rel_vid)
                except Exception as e:
                    print(f"     ⚠️ 出视频{vj+1}失败: {e}（本路跳过）")
        elif dry_run and (with_video or sc.get("video")):
            for vj in range(vid_count):
                ph = f"assets/scene_{i+1}_v{vj+1}.png"
                _placeholder_svg(os.path.join(out_dir, ph), i * 10 + vj,
                                 f"{(sc.get('title') or '')} · 视频位{vj+1}")
                videos.append(ph)

        rendered.append({
            "title": sc.get("title", f"第{i+1}幕"),
            "caption": sc.get("caption", ""),
            "image": rel_img,
            "videos": videos,
            "video": videos[0] if videos else None,
        })

    if fails:
        print(f"\n⚠️ 有 {fails} 个场景出图失败（已用占位图），请检查 ZHIPU_API_KEY / 配额 / 网络。")

    return rendered


def render_html(scenes: list[dict], out_dir: str, palette: dict, dry_run: bool) -> str:
    n = len(scenes)
    scene_divs = []
    for i, sc in enumerate(scenes):
        videos = sc.get("videos") or []
        if videos:
            cnt = len(videos)
            cls = {1: "full", 2: "split", 4: "grid"}.get(cnt, "grid")
            tiles = ""
            for v in videos:
                if dry_run:
                    tiles += f'<img class="tile" src="{v}" alt="">'
                else:
                    tiles += (f'<video class="tile" data-scrub muted playsinline preload="auto" '
                              f'poster="{sc["image"]}" src="{v}"></video>')
            media = f'<div class="media {cls}">{tiles}</div>'
        else:
            media = f'<img class="bg" src="{sc["image"]}" alt="{sc["title"]}">'
        scene_divs.append(
            f'<section class="scene" data-i="{i}">'
            f'{media}'
            f'<div class="overlay"></div>'
            f'<div class="caption">'
            f'<span class="chap">第 {i+1} 幕 / 共 {n} 幕</span>'
            f'<h1>{sc["title"]}</h1>'
            f'<p>{sc["caption"]}</p>'
            f'</div>'
            f'</section>'
        )
    scenes_html = "\n".join(scene_divs)
    dots_html = "".join(
        f'<button class="dot" data-i="{k}" aria-label="跳到第 {k+1} 幕"></button>'
        for k in range(n)
    )

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Scroll-World · 国产 scrub-engine</title>
<style id="palette">
  :root{
    --grad-a: __GRAD_A__;
    --grad-b: __GRAD_B__;
    --overlay: __OVERLAY__;
    --accent: __ACCENT__;
    --font: __FONT__;
  }
</style>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html, body { background:#000; color:#fff; font-family: var(--font); }
  #progress { position:fixed; top:0; left:0; height:4px; width:0%;
    background: linear-gradient(90deg, var(--grad-a), var(--grad-b));
    z-index:200; box-shadow:0 0 12px var(--grad-a); }
  #stage { position:sticky; top:0; height:100vh; overflow:hidden; }
  .scene { position:absolute; inset:0; opacity:0; will-change:opacity; }
  .scene .bg, .media { position:absolute; inset:0; width:100%; height:100%; }
  .media { display:grid; overflow:hidden; }
  .media.full  { grid-template-columns:1fr; }
  .media.split { grid-template-columns:1fr 1fr; }
  .media.grid  { grid-template-columns:1fr 1fr; grid-template-rows:1fr 1fr; }
  .media .tile { width:100%; height:100%; object-fit:cover; transform:scale(1.06);
    border-right:1px solid rgba(255,255,255,.08); border-bottom:1px solid rgba(255,255,255,.08); }
  .scene .bg { object-fit:cover; transform:scale(1.12); will-change:transform; }
  .overlay { position:absolute; inset:0;
    background: radial-gradient(ellipse at center, rgba(0,0,0,.08), var(--overlay)); }
  .caption { position:absolute; left:8vw; bottom:16vh; max-width:80vw;
    border-left:3px solid var(--accent); padding-left:20px;
    text-shadow:0 4px 24px rgba(0,0,0,.6); }
  .caption .chap { display:inline-block; color:var(--accent); font-size:13px;
    letter-spacing:3px; opacity:0; }
  .caption h1 { font-size:clamp(28px,5vw,64px); letter-spacing:2px; opacity:0; }
  .caption p { margin-top:12px; font-size:clamp(14px,2vw,22px); opacity:0; color:#f2f2f2; }
  .scene.active .caption .chap { animation: rise .5s ease .05s both; }
  .scene.active .caption h1   { animation: rise .6s ease .14s both; }
  .scene.active .caption p    { animation: rise .6s ease .26s both; }
  @keyframes rise { from{opacity:0; transform:translateY(30px);} to{opacity:1; transform:translateY(0);} }
  #dots { position:fixed; right:20px; top:50%; transform:translateY(-50%);
    z-index:200; display:flex; flex-direction:column; gap:14px; }
  .dot { width:11px; height:11px; padding:0; border-radius:50%;
    border:1px solid var(--accent); background:transparent; cursor:pointer; transition:all .25s; }
  .dot.current { background:var(--accent); box-shadow:0 0 12px var(--accent); transform:scale(1.35); }
  #hint { position:fixed; bottom:22px; left:50%; transform:translateX(-50%);
    font-size:13px; letter-spacing:2px; color:var(--accent); opacity:.7; z-index:200;
    animation: blink 2.2s infinite; }
  @keyframes blink { 0%,100%{opacity:.7} 50%{opacity:.2} }
</style>
</head>
<body>
<div id="progress"></div>
<nav id="dots">__DOTS__</nav>
<div id="stage">
__SCENES__
</div>
<div id="track" style="height: calc(__N__ * 100vh);"></div>
<div id="hint">↓ 滚动以 scrub 场景</div>
<script>
(function () {
  var stage = document.getElementById('stage');
  var track = document.getElementById('track');
  var scenes = Array.prototype.slice.call(stage.querySelectorAll('.scene'));
  var progress = document.getElementById('progress');
  var dots = Array.prototype.slice.call(document.querySelectorAll('#dots .dot'));
  var n = scenes.length;
  var ticking = false;

  function update() {
    ticking = false;
    var total = track.offsetHeight - window.innerHeight;
    var top = track.getBoundingClientRect().top;
    var scrolled = Math.min(Math.max(-top, 0), total);
    var p = total > 0 ? scrolled / total : 0;
    progress.style.width = (p * 100) + '%';

    var fp = p * n;
    var i = Math.floor(fp);
    var lp = fp - i;
    if (i >= n - 1) { i = n - 1; lp = 0; }

    for (var idx = 0; idx < n; idx++) {
      var s = scenes[idx];
      var op = (idx === i) ? (1 - lp) : (idx === i + 1 ? lp : 0);
      s.style.opacity = op;
      s.style.zIndex = (idx === i || idx === i + 1) ? 2 : 1;
      s.classList.toggle('active', idx === i);

      var m = s.querySelector('.media, .bg');
      if (m) {
        var shift = (idx === i) ? -lp : (idx === i + 1 ? -(1 - lp) : 0);
        m.style.transform = 'scale(1.12) translateY(' + (shift * 8) + '%)';
      }
      var vs = s.querySelectorAll('video');
      for (var k = 0; k < vs.length; k++) {
        var v = vs[k];
        if (v.duration && isFinite(v.duration)) {
          try {
            var vt = (idx === i) ? lp : (idx === i + 1 ? 1 : 0);
            v.currentTime = vt * v.duration;
          } catch (e) {}
        }
      }
      var cap = s.querySelector('.caption');
      if (cap) {
        var cy = (idx === i) ? (1 - lp) : (idx === i + 1 ? -lp : 1);
        cap.style.transform = 'translateY(' + (cy * 36) + 'px)';
        cap.style.opacity = (idx === i) ? (1 - lp * 0.4) : (idx === i + 1 ? lp : 0);
      }
    }
    for (var d = 0; d < dots.length; d++) {
      dots[d].classList.toggle('current', d === i);
    }
  }

  function onScroll() { if (!ticking) { ticking = true; requestAnimationFrame(update); } }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);

  dots.forEach(function (dot) {
    dot.addEventListener('click', function () {
      var k = parseInt(dot.getAttribute('data-i'), 10);
      var total = track.offsetHeight - window.innerHeight;
      window.scrollTo({ top: (k / n) * total, behavior: 'smooth' });
    });
  });

  scenes.forEach(function (s, idx) { if (idx !== 0) s.style.opacity = 0; });
  update();
})();
</script>
</body>
</html>
"""
    html = (html
            .replace("__SCENES__", scenes_html)
            .replace("__DOTS__", dots_html)
            .replace("__N__", str(n))
            .replace("__GRAD_A__", palette["grad_a"])
            .replace("__GRAD_B__", palette["grad_b"])
            .replace("__OVERLAY__", palette["overlay"])
            .replace("__ACCENT__", palette["accent"])
            .replace("__FONT__", palette["font"]))
    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Scroll-World 国产版 scrub-engine 构建器")
    ap.add_argument("--theme", default="未来城市", help="主题（自动派生场景）")
    ap.add_argument("--scenes", type=int, default=4, help="场景数量")
    ap.add_argument("--scenes-file", default=None, help="自定义场景 JSON 路径")
    ap.add_argument("--out", default="out/scroll_world", help="输出目录")
    ap.add_argument("--video", action="store_true", help="每个场景额外出视频并 scrub")
    ap.add_argument("--layout", choices=["full", "split", "grid"], default="full",
                    help="视频混排布局：full=整屏, split=左右2路, grid=2x2共4路")
    ap.add_argument("--palette", default=None,
                    help="配色主题（cyber/guofeng/future/nature/noir/sunset），缺省按 --theme 关键词自动匹配")
    ap.add_argument("--dry-run", action="store_true",
                    help="本地占位图，零网络零 key（离线验证 scrub 引擎）")
    args = ap.parse_args()

    if not args.dry_run:
        _load_dotenv(os.path.join(_ROOT, ".env"))
        from kernel.plugins.fabric_hub import FabricHub
        hub = FabricHub()
        # 钉死 media-gen（国产智谱），其 live 前提是有 ZHIPU_API_KEY
        if not os.environ.get("ZHIPU_API_KEY"):
            print("[警告] 未检测到 ZHIPU_API_KEY，media-gen 不可用。"
                  "请先在 .env 配置，或用 --dry-run 离线验证。", file=sys.stderr)
            return 2
    else:
        hub = None  # 占位，dry-run 不调用

    palette = pick_palette(args.theme, args.palette)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    scenes = load_scenes(args)
    print(f"场景数: {len(scenes)}  |  模式: {'dry-run' if args.dry_run else '真实(智谱)'}  "
          f"|  布局: {args.layout}  |  配色: {palette['label']}")
    rendered = generate_assets(hub, scenes, out_dir, args.dry_run, args.video, layout=args.layout)
    html_path = render_html(rendered, out_dir, palette, args.dry_run)
    dt = time.time() - t0

    print(f"\n✅ 完成 ({dt:.1f}s)")
    print(f"   页面: {html_path}")
    print(f"   资产: {os.path.join(out_dir, 'assets')}")
    print(f"   本地预览: file://{html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
