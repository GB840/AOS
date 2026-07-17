"""SkillHub 集成 —— 接入 7.9 万+ AI 技能商店。

SkillHub 是国内优先的 Skill 商店，提供加速、合规的技能搜索与安装能力。
本模块把 SkillHub CLI 包装成 AOS 可调用的适配器，支持：
- 搜索技能（优先走 SkillHub，失败回退本地）
- 安装技能到 AOS 技能目录
- 优先源策略：可配置是否优先使用 SkillHub

设计原则：
- 优雅降级：SkillHub 不可用时不影响本地技能系统
- 统一接口：和现有 find_skills / skill_creator 无缝对接
- 诚实可验证：搜索结果条数、安装状态全部真实返回
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 优先源配置：SkillHub 是国内源，CN 更快更合规
_USE_SKILLHUB_PRIORITY = os.environ.get("AOS_SKILLHUB_PRIORITY", "1") != "0"

# SkillHub CLI 路径
_SKILLHUB_BIN = os.environ.get("AOS_SKILLHUB_BIN", "")

# AOS 技能目录（安装目标）
_AOS_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills")


def _find_skillhub_bin() -> Optional[str]:
    """找到 skillhub 可执行文件。"""
    if _SKILLHUB_BIN and os.path.exists(_SKILLHUB_BIN):
        return _SKILLHUB_BIN

    # 常见路径
    candidates = [
        "skillhub",
        os.path.expandvars(r"%APPDATA%\npm\skillhub.cmd"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python314\Scripts\skillhub.exe"),
    ]

    for cmd in candidates:
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return cmd
        except Exception:
            continue

    return None


def skillhub_available() -> bool:
    """检查 SkillHub CLI 是否可用。"""
    return _find_skillhub_bin() is not None


def _run_skillhub(args: List[str], *, timeout: int = 30) -> Optional[str]:
    """运行 skillhub 命令，返回 stdout。失败返回 None。"""
    bin_path = _find_skillhub_bin()
    if not bin_path:
        return None

    try:
        result = subprocess.run(
            [bin_path] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout
        logger.debug("skillhub %s 失败: %s", args[0], result.stderr.strip())
        return None
    except subprocess.TimeoutExpired:
        logger.warning("skillhub %s 超时", args[0])
        return None
    except Exception as e:
        logger.debug("skillhub %s 异常: %s", args[0], e)
        return None


class SkillHubAdapter:
    """SkillHub 适配器。"""

    def __init__(self, *, priority: bool = None):
        self._priority = _USE_SKILLHUB_PRIORITY if priority is None else priority
        self._available = skillhub_available()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_priority(self) -> bool:
        return self._priority and self._available

    # ── 搜索 ──

    def search(self, query: str, *, limit: int = 20, sort: str = "aiScore",
               category: str = "") -> List[Dict[str, Any]]:
        """搜索技能。

        返回标准化的技能列表，每项包含：
        - id: 技能 ID（author/name）
        - name: 技能名
        - description: 描述
        - author: 作者
        - version: 版本
        - stars: Star 数
        - downloads: 下载量
        - rating: 评分
        - category: 分类
        - tags: 标签
        - source: "skillhub"
        """
        if not self._available:
            return []

        args = ["search", query, "--limit", str(limit), "--sort", sort]
        if category:
            args.extend(["--category", category])

        # 用 JSON 格式输出（如果支持的话）
        json_args = args + ["--json"]
        output = _run_skillhub(json_args, timeout=30)

        if output:
            try:
                data = json.loads(output)
                return self._normalize_results(data)
            except Exception:
                pass

        # 降级：解析文本输出
        output = _run_skillhub(args, timeout=30)
        if output:
            return self._parse_text_output(output)

        return []

    def _normalize_results(self, data: Any) -> List[Dict[str, Any]]:
        """标准化 SkillHub 返回的 JSON 数据。"""
        results = []
        items = data if isinstance(data, list) else data.get("skills", [])

        for item in items:
            results.append({
                "id": item.get("id") or item.get("name", ""),
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "author": item.get("author", ""),
                "version": item.get("version", ""),
                "stars": item.get("stars", 0),
                "downloads": item.get("downloads", 0),
                "rating": item.get("rating", 0),
                "category": item.get("category", ""),
                "tags": item.get("tags", []),
                "source": "skillhub",
                "url": item.get("url", ""),
            })

        return results

    def _parse_text_output(self, output: str) -> List[Dict[str, Any]]:
        """解析 SkillHub 的文本输出（降级方案）。"""
        results = []
        lines = output.strip().split("\n")

        for line in lines:
            line = line.strip()
            # 匹配类似 [1] author/name/category 格式的行
            if line and line[0].isdigit() and "]" in line:
                try:
                    # 提取 ID 部分（] 和 ● 之间）
                    after_bracket = line.split("]", 1)[1].strip()
                    # 找第一个空格或特殊符号前的内容
                    skill_id = after_bracket.split()[0] if after_bracket.split() else ""

                    # 提取描述（最后一段文字）
                    desc_parts = line.split("Use when")
                    desc = "Use when" + desc_parts[1] if len(desc_parts) > 1 else ""

                    parts = skill_id.split("/")
                    author = parts[0] if len(parts) > 1 else ""
                    name = parts[-1] if parts else skill_id

                    # 提取 stars（⭐ 后面的数字）
                    stars = 0
                    if "⭐" in line:
                        star_part = line.split("⭐")[1].strip()
                        star_num = ""
                        for ch in star_part:
                            if ch.isdigit() or ch in "kK.":
                                star_num += ch
                            else:
                                break
                        if star_num:
                            try:
                                stars = int(float(star_num.replace("k", "000").replace("K", "000")))
                            except Exception:
                                pass

                    results.append({
                        "id": skill_id,
                        "name": name,
                        "description": desc.strip(),
                        "author": author,
                        "version": "",
                        "stars": stars,
                        "downloads": 0,
                        "rating": 0,
                        "category": "",
                        "tags": [],
                        "source": "skillhub",
                        "url": "",
                    })
                except Exception:
                    continue

        return results

    # ── 安装 ──

    def install(self, skill_id: str, *, target_dir: str = None) -> Dict[str, Any]:
        """安装一个技能到 AOS 技能目录。

        返回安装结果：
        - ok: 是否成功
        - skill_id: 技能 ID
        - installed_path: 安装路径
        - message: 详情
        """
        if not self._available:
            return {"ok": False, "skill_id": skill_id, "message": "SkillHub CLI 不可用"}

        target_dir = target_dir or _AOS_SKILLS_DIR
        os.makedirs(target_dir, exist_ok=True)

        # 临时目录安装，再移动过去
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_skillhub(
                ["install", skill_id, "--dir", tmpdir],
                timeout=120,
            )

            if not result:
                return {
                    "ok": False,
                    "skill_id": skill_id,
                    "message": "安装失败（可能网络问题或技能不存在）",
                }

            # 找到安装的技能目录
            installed_items = os.listdir(tmpdir)
            if not installed_items:
                return {
                    "ok": False,
                    "skill_id": skill_id,
                    "message": "安装完成但未找到技能文件",
                }

            # 移动到目标目录
            skill_name = installed_items[0]
            src_path = os.path.join(tmpdir, skill_name)
            dst_path = os.path.join(target_dir, skill_name)

            try:
                if os.path.exists(dst_path):
                    shutil.rmtree(dst_path)
                shutil.move(src_path, dst_path)

                logger.info("技能安装成功: %s → %s", skill_id, dst_path)
                return {
                    "ok": True,
                    "skill_id": skill_id,
                    "installed_path": dst_path,
                    "message": f"安装成功: {skill_name}",
                }
            except Exception as e:
                logger.error("移动技能文件失败: %s", e)
                return {
                    "ok": False,
                    "skill_id": skill_id,
                    "message": f"安装失败: {e}",
                }

    # ── 分类 ──

    def list_categories(self) -> List[str]:
        """列出 SkillHub 的分类。"""
        if not self._available:
            return []

        output = _run_skillhub(["categories"], timeout=15)
        if not output:
            return []

        categories = []
        for line in output.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("-") and not line.startswith("Found"):
                categories.append(line)

        return categories

    def get_skill_info(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """获取技能详细信息。"""
        if not self._available:
            return None

        # 尝试 info 命令
        output = _run_skillhub(["info", skill_id, "--json"], timeout=15)
        if output:
            try:
                data = json.loads(output)
                results = self._normalize_results([data])
                return results[0] if results else None
            except Exception:
                pass

        output = _run_skillhub(["info", skill_id], timeout=15)
        if output:
            # 简化：从文本提取基本信息
            return {
                "id": skill_id,
                "name": skill_id.split("/")[-1] if "/" in skill_id else skill_id,
                "description": output[:500],
                "author": skill_id.split("/")[0] if "/" in skill_id else "",
                "source": "skillhub",
            }

        return None


# 单例
_adapter: Optional[SkillHubAdapter] = None


def get_skillhub_adapter() -> SkillHubAdapter:
    global _adapter
    if _adapter is None:
        _adapter = SkillHubAdapter()
    return _adapter
