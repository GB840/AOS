"""内容分发适配器（Cast）—— AOS 内容飞轮的分发层。

输入内容（视频/图文）→ 生成各平台适配的发布包 → 可人工发布或自动发布。

设计原则：
- 先有再优：MVP 先生成"发布包"，后续接 browser-use / 平台 API 自动发布
- 多平台适配：同一内容，不同平台不同标题/描述/标签/格式
- 诚实：模拟模式明确说明是"待发布"，不谎报已发布
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability, TIER_HIGH

logger = logging.getLogger(__name__)

_OUTPUT_DIR = os.environ.get(
    "AOS_CAST_OUTPUT_DIR",
    os.path.join("data", "workspaces", "fabric", "cast"),
)


def _output_dir() -> str:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return _OUTPUT_DIR


@dataclass
class PlatformPackage:
    """单个平台的发布包。"""
    platform: str
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    video_path: str = ""
    cover_path: str = ""
    published: bool = False
    publish_url: str = ""


@dataclass
class CastResult:
    """一次分发的完整结果。"""
    task_id: str
    topic: str
    packages: List[PlatformPackage] = field(default_factory=list)
    ok: bool = False
    error: str = ""


# 各平台配置：标题长度限制、描述长度、标签数量等
_PLATFORM_CONFIG = {
    "douyin": {
        "name": "抖音",
        "title_max": 55,
        "desc_max": 300,
        "tags_max": 10,
        "ratio": "9:16",
        "style": "short_vertical",
    },
    "xiaohongshu": {
        "name": "小红书",
        "title_max": 20,
        "desc_max": 1000,
        "tags_max": 15,
        "ratio": "9:16",
        "style": "lifestyle_vertical",
    },
    "bilibili": {
        "name": "B站",
        "title_max": 80,
        "desc_max": 250,
        "tags_max": 12,
        "ratio": "16:9",
        "style": "mid_horizontal",
    },
    "youtube": {
        "name": "YouTube",
        "title_max": 100,
        "desc_max": 5000,
        "tags_max": 30,
        "ratio": "16:9",
        "style": "long_horizontal",
    },
    "weibo": {
        "name": "微博",
        "title_max": 140,
        "desc_max": 2000,
        "tags_max": 5,
        "ratio": "1:1",
        "style": "square",
    },
}


class CastAdapter(BaseAgentAdapter):
    """内容分发适配器：把内容适配到各平台，生成发布包。

    MVP 阶段：生成发布包（标题/描述/标签/封面），人工发布。
    后续阶段：接入 browser-use / 平台 API，自动发布。
    """

    @property
    def engine_id(self) -> str:
        return "cast"

    def __init__(self, route_fn=None) -> None:
        self._route_fn = route_fn

    def set_route_fn(self, route_fn) -> None:
        self._route_fn = route_fn

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.CONTENT_PUBLISH, Capability.CONTENT_DISTRIBUTE]

    def health(self) -> bool:
        return True  # 生成发布包不需要外部依赖，永远可用

    def tier(self) -> str:
        return TIER_HIGH

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        topic = (payload.get("topic") or payload.get("title") or "").strip()
        video_path = payload.get("video_path") or ""
        script = payload.get("script") or ""
        platforms = payload.get("platforms") or ["douyin", "xiaohongshu", "bilibili"]
        mode = payload.get("mode") or "package"  # package: 仅生成包 / auto: 自动发布

        if not topic:
            return InvokeResult(
                ok=False,
                error="缺少 topic（内容主题）",
                engine_id=self.engine_id,
            )

        try:
            result = self.distribute(
                topic=topic,
                video_path=video_path,
                script=script,
                platforms=platforms,
                mode=mode,
            )
            return InvokeResult(
                ok=result.ok,
                data={
                    "task_id": result.task_id,
                    "topic": result.topic,
                    "packages": [
                        {
                            "platform": p.platform,
                            "title": p.title,
                            "description": p.description,
                            "tags": p.tags,
                            "video_path": p.video_path,
                            "cover_path": p.cover_path,
                            "published": p.published,
                            "publish_url": p.publish_url,
                        }
                        for p in result.packages
                    ],
                    "platform_count": len(result.packages),
                },
                engine_id=self.engine_id,
                error=result.error,
            )
        except Exception as e:  # noqa: BLE001
            return InvokeResult(
                ok=False,
                error=f"分发失败: {e}",
                engine_id=self.engine_id,
            )

    def distribute(self, *, topic: str, video_path: str = "", script: str = "",
                   platforms: List[str] = None, mode: str = "package") -> CastResult:
        """为各平台生成适配的发布包。"""
        task_id = uuid.uuid4().hex[:8]
        result = CastResult(task_id=task_id, topic=topic)
        platforms = platforms or ["douyin", "xiaohongshu", "bilibili"]

        # 为每个平台生成发布包
        for platform in platforms:
            pkg = self._generate_package(
                platform=platform,
                topic=topic,
                video_path=video_path,
                script=script,
            )
            result.packages.append(pkg)

        # 保存发布包信息到 JSON
        self._save_packages(task_id, result.packages)

        result.ok = len(result.packages) > 0
        return result

    def auto_open_publish_page(self, *, platform: str, package: Dict = None) -> Dict:
        """用 Playwright 自动打开发布页，填好内容，等待用户确认发布。

        半自动模式：系统填好所有内容，用户手动点发布按钮。
        这样既节省时间，又避免账号安全风险。
        """
        if not package:
            return {"ok": False, "error": "缺少发布包数据"}

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"ok": False, "error": "Playwright 未安装"}

        # 各平台发布页 URL
        publish_urls = {
            "douyin": "https://creator.douyin.com/creator-micro/content/upload",
            "xiaohongshu": "https://creator.xiaohongshu.com/publish/publish?source=official",
            "bilibili": "https://member.bilibili.com/platform/upload/video/frame",
            "youtube": "https://studio.youtube.com/",
        }

        url = publish_urls.get(platform)
        if not url:
            return {"ok": False, "error": f"不支持的平台: {platform}"}

        title = package.get("title", "")
        description = package.get("description", "")
        tags = package.get("tags", [])
        video_path = package.get("video_path", "")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                page.goto(url)

                # 给用户时间登录
                print(f"已打开 {platform} 发布页")
                print("请先登录账号，然后按回车继续...")
                input()

                # 尝试上传视频（如果有路径）
                if video_path and os.path.exists(video_path):
                    try:
                        # 找文件上传 input
                        upload_input = page.locator('input[type="file"]').first
                        if upload_input.is_visible():
                            upload_input.set_input_files(video_path)
                            print("视频上传中...")
                            page.wait_for_timeout(3000)
                    except Exception as e:
                        print(f"自动上传视频失败: {e}")

                # 填标题（尝试常见选择器）
                try:
                    title_selectors = [
                        'input[placeholder*="标题"]',
                        'textarea[placeholder*="标题"]',
                        '#video-title',
                        'input[name="title"]',
                    ]
                    for sel in title_selectors:
                        elem = page.locator(sel).first
                        if elem.is_visible():
                            elem.fill(title)
                            print(f"标题已填写: {title[:30]}...")
                            break
                except Exception as e:
                    print(f"填标题失败: {e}")

                # 填描述/简介
                try:
                    desc_selectors = [
                        'textarea[placeholder*="简介"]',
                        'textarea[placeholder*="描述"]',
                        'textarea[placeholder*="说说"]',
                        '#video-desc',
                    ]
                    for sel in desc_selectors:
                        elem = page.locator(sel).first
                        if elem.is_visible():
                            elem.fill(description)
                            print(f"描述已填写")
                            break
                except Exception as e:
                    print(f"填描述失败: {e}")

                print("\n✅ 内容已自动填好！")
                print("请检查内容，然后手动点击发布按钮")
                print("发布完成后，按回车关闭浏览器...")
                input()

                # 获取当前 URL 作为发布结果参考
                current_url = page.url
                browser.close()

                return {
                    "ok": True,
                    "platform": platform,
                    "auto_filled": True,
                    "publish_page_url": url,
                    "note": "内容已自动填充，请确认发布结果",
                }

        except Exception as e:
            return {"ok": False, "error": f"浏览器操作失败: {e}"}

    def _generate_package(self, *, platform: str, topic: str,
                          video_path: str = "", script: str = "") -> PlatformPackage:
        """为单个平台生成发布包。"""
        config = _PLATFORM_CONFIG.get(platform, _PLATFORM_CONFIG["douyin"])
        pkg = PlatformPackage(platform=platform)
        pkg.video_path = video_path

        # 尝试用 LLM 生成各平台适配的标题/描述/标签
        title, desc, tags = self._generate_platform_content(
            platform=platform,
            topic=topic,
            script=script,
            config=config,
        )

        pkg.title = title[:config["title_max"]] if title else topic
        pkg.description = desc[:config["desc_max"]] if desc else topic
        pkg.tags = tags[:config["tags_max"]] if tags else [topic]

        return pkg

    def _generate_platform_content(self, *, platform: str, topic: str,
                                    script: str, config: dict) -> tuple:
        """生成平台适配的内容。优先用 LLM，不可用则用模板。"""
        # 尝试用 LLM
        if self._route_fn:
            try:
                platform_name = config.get("name", platform)
                res = self._route_fn("inference.llm", {
                    "prompt": (
                        f"你是一个{platform_name}运营专家。\n\n"
                        f"视频主题: {topic}\n"
                        f"视频脚本:\n{script[:500]}\n\n"
                        f"请生成适合{platform_name}的内容：\n"
                        f"1. 标题（吸引人，有悬念，不超过{config['title_max']}字）\n"
                        f"2. 描述/简介（引发互动，不超过{config['desc_max']}字）\n"
                        f"3. 标签（{config['tags_max']}个以内，用逗号分隔，带#）\n\n"
                        f"输出格式：\n"
                        f"标题: ...\n"
                        f"描述: ...\n"
                        f"标签: #tag1 #tag2 #tag3\n"
                    ),
                })
                data = res.data if hasattr(res, "data") and res.ok else {}
                content = (data.get("content") or data.get("output") or "").strip()
                if content:
                    return self._parse_llm_content(content)
            except Exception as e:
                logger.debug("LLM 生成平台内容失败（降级模板）: %s", e)

        # 降级：模板生成
        return self._template_content(platform, topic, config)

    @staticmethod
    def _parse_llm_content(text: str) -> tuple:
        """从 LLM 输出中解析标题、描述、标签。"""
        title = ""
        desc = ""
        tags = []

        lines = text.split("\n")
        current = ""
        for line in lines:
            line = line.strip()
            if line.startswith("标题") or line.lower().startswith("title"):
                current = "title"
                parts = line.split(":", 1) if ":" in line else line.split("：", 1)
                if len(parts) > 1:
                    title = parts[1].strip()
            elif line.startswith("描述") or line.startswith("简介") or line.lower().startswith("description"):
                current = "desc"
                parts = line.split(":", 1) if ":" in line else line.split("：", 1)
                if len(parts) > 1:
                    desc = parts[1].strip()
            elif line.startswith("标签") or line.lower().startswith("tags"):
                current = "tags"
                parts = line.split(":", 1) if ":" in line else line.split("：", 1)
                if len(parts) > 1:
                    tag_str = parts[1].strip()
                    tags = [t.strip().lstrip("#") for t in tag_str.replace("，", ",").split(",") if t.strip()]
            elif current == "desc" and line:
                desc += " " + line
            elif current == "tags" and line and "#" in line:
                tags = [t.strip().lstrip("#") for t in line.replace("，", ",").split(",") if t.strip()]

        return title, desc, tags

    @staticmethod
    def _template_content(platform: str, topic: str, config: dict) -> tuple:
        """模板生成（LLM 不可用时的兜底）。"""
        templates = {
            "douyin": {
                "title": f"{topic}的秘密，99%的人不知道！",
                "desc": f"看完这条视频你就懂了。关注我，每天分享{topic}干货！",
                "tags": [topic, "干货分享", "知识科普", "涨知识", "必看"],
            },
            "xiaohongshu": {
                "title": f"关于{topic}｜保姆级教程",
                "desc": f"姐妹们！{topic}真的太重要了！\n\n今天把我整理的{topic}干货分享给大家，建议收藏慢慢看～\n\n有问题评论区见！",
                "tags": [topic, "干货", "教程", "收藏", "知识分享"],
            },
            "bilibili": {
                "title": f"【硬核科普】{topic}到底是什么？一口气讲清楚！",
                "desc": f"本期视频带你深入了解{topic}。\n\n如果觉得有用，别忘了一键三连支持一下～\n\n有什么问题欢迎在评论区讨论！",
                "tags": [topic, "科普", "知识", "干货", "科技"],
            },
            "youtube": {
                "title": f"What is {topic}? Complete Guide for Beginners",
                "desc": f"In this video, we explain {topic} in detail.\n\nLike and subscribe for more content!\n\n#ai #technology #{topic.replace(' ', '')}",
                "tags": [topic, "tutorial", "guide", "beginners", "technology"],
            },
            "weibo": {
                "title": f"#{topic}# 终于搞懂了！",
                "desc": f"关于{topic}，这篇讲透了！转发收藏～",
                "tags": [topic, "科普", "涨知识"],
            },
        }

        t = templates.get(platform, templates["douyin"])
        return t["title"], t["desc"], t["tags"]

    def _save_packages(self, task_id: str, packages: List[PlatformPackage]) -> str:
        """保存发布包信息到 JSON 文件。"""
        task_dir = os.path.join(_output_dir(), task_id)
        os.makedirs(task_dir, exist_ok=True)

        data = {
            "task_id": task_id,
            "packages": [
                {
                    "platform": p.platform,
                    "platform_name": _PLATFORM_CONFIG.get(p.platform, {}).get("name", p.platform),
                    "title": p.title,
                    "description": p.description,
                    "tags": p.tags,
                    "video_path": p.video_path,
                    "cover_path": p.cover_path,
                    "published": p.published,
                    "publish_url": p.publish_url,
                }
                for p in packages
            ],
        }

        json_path = os.path.join(task_dir, "packages.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return json_path
