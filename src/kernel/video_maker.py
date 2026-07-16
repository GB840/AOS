"""本地视频生成管线（不依赖任何付费 API）。

流程：脚本分镜 → edge-tts 配音（含逐词时间轴）→ PIL 渲染文字幻灯片
      （或用户提供的图片）→ ffmpeg 逐段烧字幕 + 拼接 → 输出 mp4。

设计约束（来自 AOS 核心理念）：
  - 不手配：缺失依赖（edge-tts / Pillow）由调用方按需自装，本模块只报清错误。
  - 诚实：生成后必须用 ffprobe 校验输出是合法 mp4，否则报失败，不假成功。
  - 跨平台：Windows / Linux 路径与字体自动探测。

外部依赖：
  - ffmpeg（已在用户机器装好，走 PATH）
  - edge-tts（pip install edge-tts）
  - Pillow（pip install Pillow）
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

# ── 路径/字体探测 ───────────────────────────────────────────────────────────


def _ffmpeg_path() -> Optional[str]:
    return shutil.which("ffmpeg")


def _ffprobe_path() -> Optional[str]:
    return shutil.which("ffprobe")


def _find_font() -> Optional[str]:
    """探测一个能渲染中文的字体文件，找不到返回 None（降级为纯色背景）。"""
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/c/Windows/Fonts/msyh.ttc",
        "/c/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    for base in ("/c/Windows/Fonts", "/usr/share/fonts"):
        if os.path.isdir(base):
            for root, _, files in os.walk(base):
                for f in files:
                    if f.lower().endswith((".ttc", ".ttf")) and any(
                        k in f.lower() for k in ("msyh", "simhei", "simsun", "noto", "cjk", "wqy")
                    ):
                        return os.path.join(root, f)
    return None


def check_deps() -> Dict[str, bool]:
    """返回各依赖是否就绪。"""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        edge = False
    else:
        edge = True
    try:
        import PIL  # noqa: F401
    except ImportError:
        pil = False
    else:
        pil = True
    return {
        "ffmpeg": _ffmpeg_path() is not None,
        "ffprobe": _ffprobe_path() is not None,
        "edge_tts": edge,
        "Pillow": pil,
    }


# ── 逐词时间轴（edge-tts WordBoundary）→ SRT ────────────────────────────────


async def _tts_segment(text: str, voice: str, audio_path: str, srt_path: str) -> float:
    """生成一段 TTS 音频 + 逐词 SRT 字幕，返回音频时长（秒）。

    edge-tts 的 WordBoundary.offset / duration 单位为 100 纳秒（ticks），
    转秒需除以 10_000_000。
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    words: List[Tuple[float, float, str]] = []
    with open(audio_path, "wb") as af:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                af.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                off = chunk.get("offset", 0) / 10_000_000.0
                dur = chunk.get("duration", 0) / 10_000_000.0
                words.append((off, off + dur, chunk.get("text", "")))

    lines = []
    for i, (start, end, w) in enumerate(words, 1):
        lines.append(f"{i}\n{_srt_time(start)} --> {_srt_time(end)}\n{w}\n")
    with open(srt_path, "w", encoding="utf-8") as sf:
        sf.write("\n".join(lines))

    dur = _probe_duration(audio_path)
    return dur or (words[-1][1] if words else 2.0)


def _srt_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _probe_duration(path: str) -> Optional[float]:
    fp = _ffprobe_path()
    if not fp:
        return None
    try:
        out = subprocess.run(
            [fp, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


# ── PIL 文字幻灯片 ──────────────────────────────────────────────────────────


def _render_text_slide(text: str, out_path: str, font_path: Optional[str],
                       size: Tuple[int, int] = (1280, 720),
                       bg: Tuple[int, int, int] = (18, 22, 33),
                       fg: Tuple[int, int, int] = (235, 238, 245)) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)

    font = None
    for fs in (48, 40, 36, 32):
        try:
            font = ImageFont.truetype(font_path, fs) if font_path else ImageFont.load_default()
            break
        except Exception:
            font = ImageFont.load_default()

    max_w = size[0] - 160
    lines: List[str] = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            test = cur + ch
            if draw.textlength(test, font=font) > max_w and cur:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        lines.append(cur)

    line_h = (font.getbbox("测")[3] - font.getbbox("测")[1]) + 14
    total_h = line_h * len(lines)
    y = max(40, (size[1] - total_h) // 2)
    for ln in lines:
        w = draw.textlength(ln, font=font)
        draw.text(((size[0] - w) // 2, y), ln, font=font, fill=fg)
        y += line_h

    img.save(out_path)


# ── ffmpeg 转义（subtitles 滤镜路径） ───────────────────────────────────────


def _sub_filter_path(p: str) -> str:
    """转义给 ffmpeg subtitles 滤镜用的路径。

    ffmpeg 的 subtitles 滤镜用 ':' 作选项分隔符、'\\' 作转义符，
    直接塞绝对路径会被误解析。统一用 filename='...' 形式：
      - Windows 绝对路径：冒号转 '\\:'，反斜杠转 '\\\\'（转义后 = 字面反斜杠）
      - 类 Unix 路径：用正斜杠
    """
    if len(p) >= 2 and p[1] == ":":
        # Windows 绝对路径（如 C:\Users\...）：保留反斜杠并正确转义
        esc = p.replace("\\", "\\\\").replace(":", "\\:")
    else:
        esc = p.replace("\\", "/")
    return f"filename='{esc}'"


# ── 主入口 ──────────────────────────────────────────────────────────────────


def generate_video(
    script: List[Dict[str, str]],
    output_path: str,
    *,
    voice: str = "zh-CN-XiaoxiaoNeural",
    font_path: Optional[str] = None,
    bg_color: Tuple[int, int, int] = (18, 22, 33),
    size: Tuple[int, int] = (1280, 720),
    timeout: int = 600,
) -> Dict[str, object]:
    """生成视频。

    script: 分镜列表，每项为 {"text": "...", "image": "可选图片路径"}
            text 为空则只用 image；image 为空则渲染文字幻灯片。
    output_path: 输出 mp4 路径。

    返回 {"ok": bool, "output": str, "duration": float, "segments": int, "error": str}
    """
    deps = check_deps()
    missing = [k for k, v in deps.items() if not v]
    if missing:
        return {"ok": False, "error": f"缺少依赖: {', '.join(missing)}（请先安装）",
                "segments": 0}

    if not script:
        return {"ok": False, "error": "script 为空", "segments": 0}

    font_path = font_path or _find_font()
    ff = _ffmpeg_path()
    if not ff:
        return {"ok": False, "error": "ffmpeg 不在 PATH", "segments": 0}

    # 工作目录放在输出文件同级（避免落到 8.3 短名临时目录，ffmpeg/libass 打不开）
    out_parent = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(out_parent, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix="aos_video_", dir=out_parent)
    clips: List[str] = []
    seg_meta: List[Dict[str, object]] = []

    try:
        for i, seg in enumerate(script):
            text = (seg.get("text") or "").strip()
            img_src = seg.get("image")
            audio = os.path.join(workdir, f"a{i}.mp3")
            srt = os.path.join(workdir, f"s{i}.srt")
            png = os.path.join(workdir, f"i{i}.png")
            clip = os.path.join(workdir, f"c{i}.mp4")

            if text:
                dur = asyncio.run(_tts_segment(text, voice, audio, srt))
            else:
                dur = 3.0
                with open(srt, "w", encoding="utf-8") as f:
                    f.write("")
                subprocess.run(
                    [ff, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100",
                     "-t", str(dur), audio],
                    capture_output=True, text=True, timeout=30,
                )

            if img_src and os.path.exists(img_src):
                png = img_src
            else:
                _render_text_slide(text or "（无文本）", png, font_path,
                                   size=size, bg=bg_color)

            # 字幕为空（edge-tts 未返回词边界）则不烧字幕，避免 ffmpeg 打不开空 srt
            has_sub = text and os.path.exists(srt) and os.path.getsize(srt) > 0
            vf = f"subtitles={_sub_filter_path(srt)}" if has_sub else "format=yuv420p"
            cmd = [
                ff, "-y", "-loop", "1", "-i", png,
                "-i", audio, "-t", f"{dur:.3f}",
                "-vf", vf,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", "-r", "30", clip,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if res.returncode != 0:
                return {"ok": False,
                        "error": f"段 {i} 编码失败: {(res.stderr or '')[-400:]}",
                        "segments": i}
            clips.append(clip)
            seg_meta.append({"index": i, "duration": round(dur, 2),
                             "text": text[:40]})

        if len(clips) == 1:
            shutil.copy(clips[0], output_path)
        else:
            filt = "".join(f"[{j}:v][{j}:a]" for j in range(len(clips)))
            filt += f"concat=n={len(clips)}:v=1:a=1[v][a]"
            cmd = [ff, "-y"]
            for c in clips:
                cmd += ["-i", c]
            cmd += ["-filter_complex", filt, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", output_path]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if res.returncode != 0:
                return {"ok": False,
                        "error": f"拼接失败: {(res.stderr or '')[-400:]}",
                        "segments": len(clips)}

        ok, info = _validate_mp4(output_path)
        if not ok:
            return {"ok": False, "error": info, "segments": len(clips)}

        return {"ok": True, "output": output_path,
                "duration": info.get("duration", 0),
                "segments": len(clips), "meta": seg_meta}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"生成异常: {e}", "segments": len(clips)}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _validate_mp4(path: str) -> Tuple[bool, Dict[str, object]]:
    fp = _ffprobe_path()
    if not fp or not os.path.exists(path):
        return False, "输出文件不存在"
    try:
        out = subprocess.run(
            [fp, "-v", "error", "-show_entries",
             "format=duration:stream=codec_type",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(out.stdout)
        has_video = any(
            s.get("codec_type") == "video" for s in data.get("streams", [])
        )
        dur = float(data.get("format", {}).get("duration", 0) or 0)
        if not has_video:
            return False, "输出缺少视频流"
        return True, {"duration": round(dur, 2), "has_video": True}
    except Exception as e:
        return False, f"校验失败: {e}"


# ── CLI 自测 ────────────────────────────────────────────────────────────────


def _demo_script() -> List[Dict[str, str]]:
    return [
        {"text": "欢迎来到 AOS 自主视频生成演示"},
        {"text": "这套流水线完全本地运行"},
        {"text": "用 edge-tts 配音 用 ffmpeg 拼接"},
        {"text": "不依赖任何付费 API"},
    ]


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "aos_demo.mp4"
    print("依赖检查:", check_deps())
    print("生成中...")
    r = generate_video(_demo_script(), out)
    print(r)
