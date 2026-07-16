"""人机协作工作流引擎（Human-in-the-Loop Workflow Engine）。

五阶段流水线，每阶段有人工确认闸门：
  Phase 1 — 意图解读（读链接/文件/上下文，提取完整需求）
  Phase 2 — 环境探测（硬件/软件/工具链，缺什么自己装）
  Phase 3 — 多方案提案（3+ 套方案，每套含工具/步骤/优劣/预估）
  Phase 4 — 执行+预览（用户选方案→执行→出预览→等审核）
  Phase 5 — 多平台发布（审核通过→B站/抖音/小红书/YouTube 一键分发）

核心理念：
  - 不手配：用户给目标，环境缺什么 AOS 自己去装
  - 不盲跑：每个关键节点等用户确认才往前走
  - 不绑定：每套方案给不同的工具栈/成本/复杂度选项
  - 千人千面：方案基于用户真实设备环境出，不是模板套话

使用方式：
  python -m kernel.workflow_engine
  （交互式，每阶段自动停下等待确认）

或编程调用：
  engine = WorkflowEngine()
  engine.phase1_intent("模仿这个视频风格做一个产品介绍 https://youtube.com/xxx")
  engine.phase2_probe()  → 返回环境报告
  engine.phase3_plans()  → 生成 3 套方案
  engine.phase4_execute(plan_index)  → 执行并出预览
  engine.phase5_publish()  → 发布到各平台
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---- 状态管理 ----------------------------------------------------

_STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "_workflow_state")


@dataclass
class WorkflowState:
    """工作流状态——可序列化，支持中断后继续。"""
    task_id: str = ""
    user_input: str = ""                    # 用户原始输入
    intent: Dict[str, Any] = field(default_factory=dict)   # Phase 1 产物
    environment: Dict[str, Any] = field(default_factory=dict)  # Phase 2 产物
    plans: List[Dict[str, Any]] = field(default_factory=list)  # Phase 3 产物
    chosen_plan: int = -1                   # 用户选的方案索引
    execution_result: Dict[str, Any] = field(default_factory=dict)  # Phase 4 产物
    approved: bool = False                  # 审核是否通过
    publish_results: Dict[str, Any] = field(default_factory=dict)  # Phase 5 产物
    current_phase: int = 0
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = ""


# ---- 环境探测 ------------------------------------------------

def probe_environment() -> Dict[str, Any]:
    """探测用户设备的真实软硬件环境。

    不假设、不编造——每条数据都是真实运行命令获得的。
    探测结果直接影响 Phase 3 方案生成的质量。
    """
    env = {
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }

    # ---- GPU ----
    gpu_info = []
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpu_info.append({
                        "name": parts[0], "memory": parts[1],
                        "driver": parts[2], "type": "NVIDIA",
                    })
    except Exception:
        pass
    env["gpu"] = gpu_info

    # ---- RAM ----
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["wmic", "computersystem", "get", "totalphysicalmemory"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                digits = re.search(r"\d+", line)
                if digits:
                    gb = int(digits.group()) / (1024 ** 3)
                    env["ram_gb"] = round(gb, 1)
                    break
    except Exception:
        env["ram_gb"] = "unknown"

    # ---- Disk ----
    try:
        usage = shutil.disk_usage(os.path.expanduser("~"))
        env["disk_free_gb"] = round(usage.free / (1024 ** 3), 1)
        env["disk_total_gb"] = round(usage.total / (1024 ** 3), 1)
    except Exception:
        env["disk_free_gb"] = "unknown"

    # ---- Python ----
    env["python_version"] = sys.version.split()[0]
    env["python_path"] = sys.executable

    # ---- 已安装的关键软件（用于方案生成） ----
    tools = {}
    tool_checks = {
        "ffmpeg": ["ffmpeg", "-version"],
        "node": ["node", "--version"],
        "npm": ["npm", "--version"],
        "git": ["git", "--version"],
        "docker": ["docker", "--version"],
        "imagemagick": ["magick", "--version"],
        "winget": ["winget", "--version"],
        "choco": ["choco", "--version"],
        "conda": ["conda", "--version"],
        "ollama": ["ollama", "--version"],
    }
    for name, cmd in tool_checks.items():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0][:80]
                tools[name] = version_line
        except Exception:
            pass
    env["installed_tools"] = tools

    # ---- 网络 ----
    env["has_network"] = _check_network()

    return env


def _check_network() -> bool:
    try:
        subprocess.run(["ping", "-n", "1", "-w", "2000", "8.8.8.8"],
                       capture_output=True, timeout=3)
        return True
    except Exception:
        return False


def format_env_report(env: Dict[str, Any]) -> str:
    """生成可读的环境报告。"""
    lines = [
        f"操作系统: {env.get('os', '?')} {env.get('os_release', '')}",
        f"Python: {env.get('python_version', '?')}",
        f"内存: {env.get('ram_gb', '?')} GB",
        f"磁盘: {env.get('disk_free_gb', '?')} GB 可用 / {env.get('disk_total_gb', '?')} GB 总量",
    ]
    gpu = env.get("gpu", [])
    if gpu:
        for g in gpu:
            lines.append(f"GPU: {g['name']} ({g['memory']}, {g['type']})")
    else:
        lines.append("GPU: 未检测到独立显卡")
    tools = env.get("installed_tools", {})
    if tools:
        lines.append(f"已装工具: {', '.join(tools.keys())}")
    lines.append(f"网络: {'通' if env.get('has_network') else '断'}")
    return "\n".join(lines)


def install_missing(tool_name: str) -> Tuple[bool, str]:
    """尝试自动安装缺失的工具。返回 (成功, 消息)。"""
    installers = {
        "ffmpeg": "winget install ffmpeg",
        "node": "winget install OpenJS.NodeJS.LTS",
        "git": "winget install Git.Git",
        "imagemagick": "winget install ImageMagick.ImageMagick",
        "choco": 'powershell -c "Set-ExecutionPolicy Bypass -Scope Process; [System.Net.ServicePointManager]::SecurityProtocol = 3072; iex ((New-Object System.Net.WebClient).DownloadString(\'https://community.chocolatey.org/install.ps1\'))"',
    }
    cmd = installers.get(tool_name)
    if not cmd:
        return False, f"不知道该工具 {tool_name} 的安装方式"

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return True, f"{tool_name} 安装成功"
        return False, f"安装失败: {result.stderr[:200]}"
    except Exception as e:
        return False, str(e)


# ---- 意图解读 -------------------------------------------------

def analyze_intent(user_input: str, env: Dict[str, Any]) -> Dict[str, Any]:
    """解读用户意图——通用、任务无关。

    设计要点（灵活性核心）：
      不把意图分类成固定任务类型（video/install/deploy/file_ops...），
      只提取「目标 + 参考材料 + 环境」。至于「怎么做」，完全交给后续的
      LLM 方案生成 + 通用能力路由（autopilot）去自适应。
      这样每个人给的任务不一样，系统都能接住，而不是走预设的类型分支。

    返回结构化意图。若 needs_clarification=True，Phase 1 会反问用户。
    """
    intent = {
        "raw": user_input,
        "type": "general",          # 仅作 LLM 上下文提示，绝不用于分支路由
        "domain": "general",
        "goal": user_input,
        "reference_urls": [],
        "reference_type": None,
        "needs_clarification": False,
        "clarification_question": "",
        "local_context": {},
        "category_hint": "",        # 轻量提示(视频/代码/文件/部署...)，仅供 LLM 参考
    }

    # 提取 URL
    urls = re.findall(r"https?://[^\s]+", user_input)
    intent["reference_urls"] = urls

    # 本地路径扫描（让方案生成有本地素材上下文）
    _scan_local(intent, user_input)

    # 参考内容抓取（让方案生成有料）
    if urls:
        intent["reference_content"] = _fetch_url_content(urls[0])

    # 轻量分类提示：只喂给 LLM 出方案用，永不用于 if/elif 分派
    intent["category_hint"] = _category_hint(user_input, intent)

    # 意图不明才澄清：没有清晰动作动词、又没有本地上下文时才反问。
    # 反问用开放式问题（不预设 a/b/c 菜单），保持灵活性。
    if not _has_clear_action(user_input) and not intent.get("local_context"):
        intent["needs_clarification"] = True
        intent["clarification_question"] = (
            f"我没完全理解「{user_input[:60]}」具体要做什么。能再描述一下吗？\n"
            "  你想要达到什么效果？\n"
            "  涉及什么类型的文件/内容？\n"
            "  有没有参考链接或本地路径？"
        )

    return intent


def _category_hint(user_input: str, intent: Dict[str, Any]) -> str:
    """轻量分类提示（仅供 LLM 出方案参考，绝不用于代码分支）。"""
    text = user_input.lower()
    if any(k in text for k in ["视频", "剪辑", "vlog", "字幕", "配音", "短视频"]):
        return "video"
    if any(k in text for k in ["部署", "上线", "服务器", "docker", "k8s", "nginx"]):
        return "deployment"
    if any(k in text for k in ["装", "安装", "install", "setup", "配置环境"]):
        return "installation"
    if any(k in text for k in ["整理", "分类", "删除", "压缩", "打包", "去重", "改名", "批量"]):
        return "file_ops"
    if any(k in text for k in ["代码", "脚本", "爬虫", "程序", "函数", "api"]):
        return "software"
    if intent.get("reference_urls") and any(
        d in intent["reference_urls"][0].lower() for d in ["github.com", "gitlab.com"]
    ):
        return "code_repo"
    return "general"


def _scan_local(intent: Dict[str, Any], user_input: str) -> None:
    """扫描用户提到的本地路径/盘符，返回文件统计。"""
    # 匹配盘符或路径
    path_patterns = [
        r"([A-Za-z])\s*[盘:]",      # D盘 / D:
        r"([A-Za-z]:[/\\]\S*)",      # D:\path
    ]
    target = None
    for pat in path_patterns:
        m = re.search(pat, user_input)
        if m:
            target = m.group(1) if "盘" in pat else m.group(0).rstrip(".,;")
            break

    if not target:
        return

    # 如果只是盘符 → 补全为根目录
    if len(target) == 1:
        target = target + ":\\"

    scan_result = _scan_directory(target)
    if scan_result:
        intent["local_context"] = scan_result
        by_type = scan_result.get("by_type", {})
        # 图片类型检测
        img_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".ico", ".heic"}
        img_count = sum(n for ext, n in by_type.items() if ext in img_exts)
        # 视频类型检测
        vid_exts = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"}
        vid_count = sum(n for ext, n in by_type.items() if ext in vid_exts)

        if img_count > 10:
            intent["needs_clarification"] = True
            intent["clarification_question"] = (
                f"检测到 {target} 下有 {img_count} 张图片"
                f"({', '.join(f'{e}({n})' for e, n in by_type.items() if e in img_exts)})。"
                "你想对它们做什么？请直接描述你的目标（例如：做成视频、按类型分类、压缩打包、去重…）。"
            )
        elif vid_count > 0:
            intent["needs_clarification"] = True
            intent["clarification_question"] = (
                f"检测到 {target} 下有 {vid_count} 个视频。你想对它们做什么？"
                "请直接描述你的目标（例如：合并、转格式、提取音频、压缩…）。"
            )


def _scan_directory(path: str) -> Optional[Dict[str, Any]]:
    """扫描目录，返回文件统计。大目录只扫浅层，防卡死。"""
    try:
        if not os.path.exists(path):
            return {"error": f"路径不存在: {path}", "exists": False}

        # 磁盘根目录只扫直接子项（不递归），否则 os.walk 在 D:\ 会卡几分钟
        is_root = len(path) <= 3 and path[1] == ":"

        sample_files = []
        by_type: Dict[str, int] = {}
        total_count = 0
        total_size = 0
        start = time.time()
        max_time = 5  # 最多 5 秒
        max_depth = 0 if is_root else 2

        for root, dirs, filenames in os.walk(path):
            if time.time() - start > max_time:
                break
            depth = root.replace(path, "").count(os.sep)
            if depth > max_depth:
                del dirs[:]
                continue
            for f in filenames:
                if time.time() - start > max_time:
                    break
                fp = os.path.join(root, f)
                try:
                    size = os.path.getsize(fp)
                except OSError:
                    continue
                ext = os.path.splitext(f)[1].lower() or "(无扩展名)"
                by_type[ext] = by_type.get(ext, 0) + 1
                total_size += size
                total_count += 1
                if len(sample_files) < 10:
                    sample_files.append({"name": f, "ext": ext, "size": size, "path": fp})

        top_types = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:15]
        return {
            "path": path,
            "exists": True,
            "total_files": total_count,
            "total_size_mb": round(total_size / (1024 * 1024), 1),
            "by_type": dict(top_types),
            "sample_files": [f["name"] for f in sample_files[:5]],
        }
    except Exception as e:
        return {"error": str(e), "exists": False}


def _has_clear_action(text: str) -> bool:
    """检查输入是否包含明确操作指令。"""
    action_kw = ["模仿", "做", "制作", "生成", "创建", "分析", "提取", "下载",
                 "make", "create", "generate", "analyze", "download", "仿"]
    return any(kw in text.lower() for kw in action_kw)


def _apply_clarification(intent: Dict[str, Any], answer: str) -> Dict[str, Any]:
    """用户回答了澄清问题。

    现在澄清是开放式问题（非 a/b/c 菜单），所以这里只把用户补充并入
    目标、并解除澄清标记——不再做「字母→任务类型」的硬编码映射
    （那才是反灵活性的根源）。具体怎么做交给后续 LLM 方案生成。
    """
    answer = answer.strip()
    if not answer or answer_lower(answer) in ("q", "退出", "exit"):
        # 用户想退出，保持澄清态由调用方处理
        return intent
    # 把补充信息并入目标，供后续 LLM 出方案
    intent["goal"] = f"{intent.get('goal', '')} —— 用户补充: {answer}"
    intent["needs_clarification"] = False
    return intent


def answer_lower(s: str) -> str:
    return s.strip().lower()


def _extract_goal_from_input(text: str) -> str:
    """从用户输入中提取核心目标（去掉 URL 部分）。"""
    cleaned = re.sub(r"https?://[^\s]+", "", text).strip()
    return cleaned or text


def _fetch_url_content(url: str) -> Optional[str]:
    """尝试获取 URL 内容摘要。"""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "AOS-Workflow/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            # 提取 title
            title_m = re.search(r"<title[^>]*>(.*?)</title>", content, re.I | re.S)
            title = title_m.group(1).strip() if title_m else ""
            # 提取 meta description
            desc_m = re.search(
                r'<meta[^>]*name="description"[^>]*content="([^"]*)"', content, re.I
            )
            desc = desc_m.group(1) if desc_m else ""
            return f"title: {title[:200]}\ndescription: {desc[:500]}"
    except Exception as e:
        return f"无法获取内容: {str(e)[:200]}"


# ---- 多方案生成 -----------------------------------------------

def generate_plans(intent: Dict[str, Any], env: Dict[str, Any]) -> List[Dict[str, Any]]:
    """基于意图和环境，生成 3+ 套差异化执行方案（通用、任务无关）。

    主路径：LLM 根据「目标 + 环境 + 可用能力」产出 3 套真正不同的方案
    （自动化程度/成本/质量/耗时各异）。LLM 不可用 → 回落 3 套通用方案。

    关键：不使用任何「任务类型 → 模板」的硬编码分支。无论用户给的是
    「装 ffmpeg」「做视频」「写爬虫」「部署服务」还是任何其它任务，
    都走同一条通用生成路径，因此每个人想弄的都不一样也能接住。
    """
    plans = _llm_generate_plans(intent, env)
    if not plans:
        plans = _universal_fallback_plans(intent, env)

    # LLM 增强（可选，失败不影响主流程）
    plans = _llm_enhance_plans(plans, intent, env)
    return plans


def _llm_generate_plans(intent: Dict[str, Any], env: Dict[str, Any]) -> List[Dict[str, Any]]:
    """用 LLM 为任意任务生成 3 套差异化方案。无 key / 不可用返回 []。"""
    try:
        from openai import OpenAI
        api_key = os.environ.get("ZHIPU_API_KEY", "")
        if not api_key:
            return []
        client = OpenAI(api_key=api_key, base_url="https://open.bigmodel.cn/api/paas/v4")

        env_summary = format_env_report(env)
        goal = intent.get("goal", "")
        refs = intent.get("reference_urls", [])
        ref_content = str(intent.get("reference_content", ""))[:1500]

        prompt = (
            "你是 AOS 自主智能体的方案规划器。用户给了一个开放式任务，"
            "请基于用户真实环境，生成 3 套**真正不同**的执行方案。\n\n"
            f"用户目标: {goal}\n"
            f"参考链接: {refs}\n"
            f"参考内容摘要: {ref_content}\n"
            f"用户环境:\n{env_summary}\n\n"
            "AOS 可用的通用能力与工具（请按需组合，不必全用）:\n"
            "  - web.search: 联网搜索\n"
            "  - 终端/代码执行(action.code_exec): 可运行 Windows/Linux 命令、"
            "pip/winget/choco 安装、python/node 脚本、git 等\n"
            "  - inference.llm: LLM 推理 / 生成文本 / 写代码\n"
            "  - 已装工具见上方环境列表；缺什么可现场安装\n"
            "  - 视频相关任务可调用本地模块 kernel.video_maker "
            "(generate_video(script, out_path)，script 为分镜文本列表)\n\n"
            "要求每套方案给出: name, approach, tools_needed(列表), "
            "steps(列表, 具体可执行), pros(列表), cons(列表), "
            "estimated_time, suitability, missing_tools(列表, 基于环境判断)。\n"
            "三套方案要在「自动化程度 / 成本 / 质量 / 耗时」上有明显差异。"
            "只返回 JSON 数组，不要任何解释或 markdown 包裹。"
        )
        resp = client.chat.completions.create(
            model="glm-4-flash", temperature=0.4, max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content
        json_match = re.search(r"\[.*\]", text, re.S)
        if not json_match:
            return []
        plans = json.loads(json_match.group())
        for i, p in enumerate(plans):
            p["id"] = i
            p.setdefault("name", f"方案{i+1}")
            p.setdefault("steps", [])
            p.setdefault("tools_needed", [])
            p.setdefault("pros", [])
            p.setdefault("cons", [])
            p.setdefault("missing_tools", [])
        return plans[:5]
    except Exception:
        logger.warning("LLM 生成方案失败，回落通用模板", exc_info=True)
        return []


def _universal_fallback_plans(intent: Dict[str, Any], env: Dict[str, Any]) -> List[Dict[str, Any]]:
    """LLM 不可用时的通用回落：3 套适用于任何任务的方案（无任务假设）。"""
    goal = intent.get("goal", "")
    return [{
        "id": 0, "name": "方案A: 全自动执行（推荐）",
        "approach": f"AOS 自动搜索→分析→安装→执行→验证，目标: {goal[:50]}",
        "tools_needed": [],
        "steps": [
            f"1. 搜索「{goal[:40]}」相关最佳实践",
            "2. 分析搜索结果，提取具体执行步骤",
            "3. 安装缺失的工具/依赖",
            "4. 执行核心任务",
            "5. 验证结果并汇报",
        ],
        "pros": ["零人工", "自动纠错", "学习积累"],
        "cons": ["复杂任务可能走偏"],
        "estimated_time": "5-15 分钟",
        "suitability": "常规任务",
        "missing_tools": [],
    }, {
        "id": 1, "name": "方案B: 分步确认",
        "approach": "每步执行前先展示计划，你确认后才继续",
        "tools_needed": [],
        "steps": [
            "1. 搜索相关信息并展示结果",
            "2. 等你确认搜索方向正确",
            "3. 执行第一步操作",
            "4. 等你确认结果",
            "5. 继续后续步骤",
        ],
        "pros": ["可控", "可随时中断"],
        "cons": ["慢", "需要频繁确认"],
        "estimated_time": "15-30 分钟",
        "suitability": "高风险/复杂任务",
        "missing_tools": [],
    }, {
        "id": 2, "name": "方案C: 仅出方案不执行",
        "approach": "只搜索最佳实践输出详细步骤，不自动执行",
        "tools_needed": [],
        "steps": [
            "1. 搜索最佳实践",
            "2. 分析并整理成可执行文档",
            "3. 输出 Markdown 格式方案",
        ],
        "pros": ["最安全", "适合学习"],
        "cons": ["不会自动执行"],
        "estimated_time": "2-5 分钟",
        "suitability": "调研/学习场景",
        "missing_tools": [],
    }]


def _llm_enhance_plans(plans, intent, env):
    """用 LLM 增强方案描述。如果无 LLM，保持原始模板。"""
    try:
        from openai import OpenAI
        api_key = os.environ.get("ZHIPU_API_KEY", "")
        if not api_key:
            return plans
        client = OpenAI(api_key=api_key, base_url="https://open.bigmodel.cn/api/paas/v4")

        env_summary = format_env_report(env)
        plans_text = json.dumps(plans, ensure_ascii=False, indent=2)

        prompt = (
            "User intent: " + intent.get('goal', '') + "\n"
            "Task type: " + intent.get('type', '') + "\n"
            "Environment: " + env_summary + "\n"
            "Draft plans:\n" + plans_text[:2000] + "\n\n"
            "Improve these plans to better fit this user's environment.\n"
            "Focus: 1) Mark each plan as suitable/unsuitable for this device\n"
            "2) Missing tool install commands must be OS-specific\n"
            "3) Time estimates should reflect this device's performance\n"
            "Return JSON array, keep id/name/approach/pros/cons/estimated_time/suitability for each."
        )
        resp = client.chat.completions.create(
            model="glm-4-flash", temperature=0.3, max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        enhanced = resp.choices[0].message.content
        # 尝试解析 JSON
        json_match = re.search(r"\[.*\]", enhanced, re.S)
        if json_match:
            new_plans = json.loads(json_match.group())
            # 合并：保留原始结构的完整性，用 LLM 的改进覆盖文本
            for i, p in enumerate(plans):
                if i < len(new_plans):
                    for key in ("pros", "cons", "estimated_time", "suitability", "approach"):
                        if key in new_plans[i]:
                            p[key] = new_plans[i][key]
            return plans
    except Exception:
        logger.warning("LLM 增强方案失败", exc_info=True)
    return plans


# ---- 工作流引擎主类 --------------------------------------------

class WorkflowEngine:
    """五阶段人机协作工作流引擎。

    每阶段有明确的输入→处理→输出→确认闸门。
    状态持久化到磁盘，支持中断后恢复。
    """

    def __init__(self) -> None:
        self.state = WorkflowState()
        self._on_confirm: Optional[Callable] = None

    @property
    def state_file(self) -> str:
        tid = self.state.task_id or "current"
        return os.path.join(_STATE_DIR, f"wf_{tid}.json")

    def save(self) -> None:
        """保存当前状态。"""
        self.state.updated_at = datetime.datetime.now().isoformat()
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state.__dict__, f, ensure_ascii=False, indent=2)

    def load(self, task_id: str) -> bool:
        """恢复之前的状态。"""
        path = os.path.join(_STATE_DIR, f"wf_{task_id}.json")
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.state = WorkflowState(**data)
        return True

    def phase1_intent(self, user_input: str) -> Dict[str, Any]:
        """Phase 1: 意图解读。

        读链接、文件、上下文，提取完整结构化需求。
        如果是 YouTube/视频链接，尝试获取视频信息。
        """
        self.state.user_input = user_input
        env = self.state.environment or probe_environment()
        self.state.environment = env

        self.state.intent = analyze_intent(user_input, env)
        self.state.current_phase = 1
        self.save()
        return self.state.intent

    def phase2_probe(self) -> Dict[str, Any]:
        """Phase 2: 环境探测。

        检测硬件/软件/工具链，缺失的关键工具自动安装。
        """
        env = probe_environment()
        self.state.environment = env
        self.state.current_phase = 2

        # 自动装缺失的关键工具
        installed = []
        for tool in ["ffmpeg", "git"]:
            if tool not in env.get("installed_tools", {}):
                ok, msg = install_missing(tool)
                if ok:
                    installed.append(tool)
                else:
                    logger.warning("自动安装 %s 失败: %s", tool, msg)

        if installed:
            # 重新探测
            env = probe_environment()
            self.state.environment = env

        self.save()
        return env

    def phase3_plans(self) -> List[Dict[str, Any]]:
        """Phase 3: 多方案生成。

        基于意图+环境生成 3+ 套方案。每套含工具需求/步骤/优劣/预估。
        """
        if not self.state.intent:
            raise RuntimeError("先跑 Phase 1/2")

        plans = generate_plans(self.state.intent, self.state.environment)
        self.state.plans = plans
        self.state.current_phase = 3
        self.save()
        return plans

    def phase4_execute(self, plan_index: int) -> Dict[str, Any]:
        """Phase 4: 执行选中方案。

        先装缺失工具 → 调用 autopilot 真执行 → 返回结果。
        """
        if plan_index < 0 or plan_index >= len(self.state.plans):
            return {"error": f"方案索引 {plan_index} 无效"}

        self.state.chosen_plan = plan_index
        plan = self.state.plans[plan_index]
        self.state.current_phase = 4

        # 先装缺失工具
        missing = plan.get("missing_tools", [])
        installed = []
        for tool in missing:
            ok, msg = install_missing(tool)
            if ok:
                installed.append(tool)

        # 通用执行（灵活性核心）：
        # 不按任务类型分支——视频/爬虫/部署/分析/任何任务都走同一条自主管道。
        # 把选中方案的「目标 + 具体步骤」交给 autopilot / learning_loop，
        # 由 LLM 规划器决定如何组合 搜索/代码执行/推理 等通用能力来完成。
        # 若任务需要视频，方案生成阶段已把 kernel.video_maker 调用写进 steps，
        # 这里统一执行，无需专属分支。
        goal = self.state.intent.get("goal", self.state.user_input)
        steps_text = "\n".join(plan.get("steps", []))
        task = f"执行方案「{plan['name']}」\n目标: {goal}\n步骤:\n{steps_text}"

        try:
            from kernel.learning_loop import LearningLoop
            loop = LearningLoop(max_retries=2)
            result = loop.run(task, planner="ag2")
            self.state.execution_result = {
                "plan": plan["name"],
                "plan_index": plan_index,
                "missing_tools_installed": installed,
                "status": "executed",
                "autopilot_result": result,
            }
        except Exception as e:
            logger.warning("LearningLoop 不可用，降级 autopilot: %s", e)
            try:
                from kernel.autopilot import run as autopilot_run
                result = autopilot_run(task)
                self.state.execution_result = {
                    "plan": plan["name"],
                    "plan_index": plan_index,
                    "missing_tools_installed": installed,
                    "status": "executed",
                    "autopilot_result": result,
                }
            except Exception as e2:
                self.state.execution_result = {
                    "error": f"执行失败: {e2}",
                    "status": "failed",
                }

        self.save()
        return self.state.execution_result

    def _detect_artifacts(self, result: Dict[str, Any]) -> List[Dict[str, str]]:
        """从执行结果里提取产出的文件（通用：视频/图片/csv/zip 等都可）。

        不预设只认视频——任何任务产出的文件都一视同仁地回报给用户。
        """
        artifacts = []
        # 1) 扫描 video_maker 的输出目录（若任务生成了视频）
        out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "_video_output")
        if os.path.isdir(out_dir):
            for f in sorted(os.listdir(out_dir)):
                fp = os.path.join(out_dir, f)
                if os.path.isfile(fp) and f.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".png", ".jpg")):
                    artifacts.append({"type": "media", "path": fp})
        # 2) 从 autopilot 最终输出里找疑似路径
        final = (result.get("execution", {}).get("final") or "") if isinstance(result, dict) else ""
        for m in re.findall(r"([A-Za-z]:[\\/][^\s\"']+\.[a-zA-Z0-9]{1,5}|/[^\s\"']+\.[a-zA-Z0-9]{1,5})", str(final)):
            if os.path.exists(m):
                artifacts.append({"type": "file", "path": m})
        # 去重
        seen = set()
        uniq = []
        for a in artifacts:
            if a["path"] not in seen:
                seen.add(a["path"])
                uniq.append(a)
        return uniq

    def phase5_publish(self, platforms: List[str] | None = None) -> Dict[str, Any]:
        """Phase 5: 审核通过后发布到各平台。"""
        if not self.state.approved:
            return {"error": "未通过审核，不能发布"}

        platforms = platforms or ["bilibili", "douyin", "xiaohongshu"]
        results = {}
        for p in platforms:
            results[p] = {"status": "pending", "note": f"发布到 {p}（API 对接后续迭代）"}
        self.state.publish_results = results
        self.state.current_phase = 5
        self.save()
        return results

    def confirm(self, approved: bool) -> None:
        """用户确认闸门。"""
        self.state.approved = approved
        self.save()


# ---- CLI 交互入口 ---------------------------------------------

def _print_phase_header(phase: int, title: str) -> None:
    print(f"\n{'='*60}")
    print(f" Phase {phase}: {title}")
    print(f"{'='*60}")


def _print_plans(plans: List[Dict[str, Any]]) -> None:
    for p in plans:
        print(f"\n  📋 {p['name']}")
        print(f"     方法: {p.get('approach', 'N/A')}")
        if p.get("tools_needed"):
            print(f"     需要: {', '.join(p['tools_needed'])}")
        missing = p.get("missing_tools", [])
        if missing:
            print(f"     ⚠️  缺失: {', '.join(missing)}（将自动安装）")
        print(f"     优势: {', '.join(p.get('pros', []))}")
        print(f"     劣势: {', '.join(p.get('cons', []))}")
        print(f"     预估: {p.get('estimated_time', 'N/A')}")
        print(f"     适合: {p.get('suitability', 'N/A')}")


def main() -> None:
    """交互式 CLI 入口。"""
    print("🧠 AOS 人机协作工作流引擎")
    print("   五阶段: 意图解读 → 环境探测 → 多方案 → 执行 → 发布")
    print("   每阶段自动停下等待你确认\n")

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    except Exception:
        pass

    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    else:
        user_input = input("🎯 请输入任务（可以是链接/描述/文件路径）: ").strip()

    if not user_input:
        print("任务不能为空")
        sys.exit(1)

    engine = WorkflowEngine()
    env = probe_environment()

    # ---- Phase 1: 意图解读（含澄清循环） ----
    intent = engine.phase1_intent(user_input)
    while intent.get("needs_clarification"):
        _print_phase_header(1, "意图解读 — 需要确认")
        if intent.get("local_context"):
            lc = intent["local_context"]
            print(f"  📁 扫描 {lc.get('path')}: {lc.get('total_files')} 个文件, "
                  f"{lc.get('total_size_mb')} MB")
            by_type = lc.get("by_type", {})
            if by_type:
                top3 = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:5]
                print(f"     文件类型: {', '.join(f'{ext}({n})' for ext, n in top3)}")
            if lc.get("sample_files"):
                print(f"     示例: {', '.join(lc['sample_files'][:5])}")
        print(f"\n  ❓ {intent['clarification_question']}")
        answer = input("\n  你的选择 (a/b/c/d/e 或直接描述): ").strip()
        if not answer or answer.lower() == "q":
            print("已退出")
            sys.exit(0)
        # 尝试用澄清映射把 a/b/c 解析成具体意图
        intent = _apply_clarification(intent, answer)
        if not intent.get("needs_clarification"):
            break  # 映射成功，退出澄清循环
        # 映射失败 → 合并用户补充到原始输入，重新分析
        user_input = f"{user_input} —— 用户补充: {answer}"
        intent = engine.phase1_intent(user_input)

    _print_phase_header(1, "意图解读")
    print(f"  类别提示: {intent.get('category_hint') or 'general'}（仅供参考，不用于分支）")
    print(f"  目标: {intent.get('goal', '')[:100]}")
    lc = intent.get("local_context", {})
    if lc and lc.get("total_files"):
        print(f"  本地: {lc.get('total_files')} 文件, {lc.get('total_size_mb')} MB")
    if intent.get("reference_content"):
        ref = str(intent["reference_content"])[:200]
        print(f"  参考: {ref}")
    input("\n  [Enter] 继续 → Phase 2 环境探测")

    # ---- Phase 2 ----
    _print_phase_header(2, "环境探测")
    env = engine.phase2_probe()
    print(f"  {format_env_report(env)}")
    input("\n  [Enter] 继续 → Phase 3 方案生成")

    # ---- Phase 3 ----
    _print_phase_header(3, "多方案提案")
    plans = engine.phase3_plans()
    _print_plans(plans)

    choice = input(f"\n  选择方案 (A/B/C 或 0-{len(plans)-1}) 或 q 退出: ").strip()
    if choice.lower() == "q":
        print("已保存状态，下次可恢复")
        sys.exit(0)
    idx = _parse_choice(choice, len(plans))
    if idx is None:
        print("无效选择")
        sys.exit(1)

    # ---- Phase 4 ----
    _print_phase_header(4, "执行")
    print(f"  ⚡ 正在执行方案 {idx}「{plans[idx]['name']}」...")
    result = engine.phase4_execute(idx)
    if result.get("status") == "executed":
        ar = result.get("autopilot_result", {})
        print(f"  规划器: {ar.get('planner', '?')}")
        exe = ar.get("execution", {})
        print(f"  结果: {exe.get('ok_steps', 0)} 成功 / {exe.get('failed_steps', 0)} 失败")
        print(f"  耗时: {ar.get('duration_s', ar.get('total_duration_s', '?'))}s")
        # 通用产物检测：任何任务产出的文件都回报（视频/图片/csv/...）
        arts = engine._detect_artifacts(ar)
        for a in arts:
            print(f"  📦 产出文件: {a['path']}")
        if ar.get("final"):
            print(f"  产出摘要: {str(ar.get('final'))[:200]}")
    else:
        print(f"  ❌ 执行失败: {result.get('error', '未知错误')}")

    approval = input("\n  审核通过？(y/n): ").strip().lower()
    if approval == "y":
        engine.confirm(True)
        _print_phase_header(5, "多平台发布")
        pub = engine.phase5_publish()
        print(f"  {json.dumps(pub, ensure_ascii=False, indent=2)}")
        print("\n✅ 工作流完成！")
    else:
        print("❌ 审核未通过，工作流暂停。状态已保存。")

    print(f"\n状态文件: {engine.state_file}")


def _parse_choice(choice: str, max_idx: int) -> Optional[int]:
    """解析用户选择：支持 0/1/2 和 A/B/C/a/b/c。"""
    choice = choice.strip().upper()
    if choice in ("A", "B", "C", "D", "E", "F"):
        idx = ord(choice) - ord("A")
        return idx if idx < max_idx else None
    try:
        idx = int(choice)
        return idx if 0 <= idx < max_idx else None
    except ValueError:
        return None

    # Phase 4
    _print_phase_header(4, "执行")
    result = engine.phase4_execute(idx)
    print(f"  {json.dumps(result, ensure_ascii=False, indent=2)}")

    approval = input("\n  审核通过？(y/n): ").strip().lower()
    if approval == "y":
        engine.confirm(True)
        # Phase 5
        _print_phase_header(5, "多平台发布")
        pub = engine.phase5_publish()
        print(f"  {json.dumps(pub, ensure_ascii=False, indent=2)}")
        print("\n✅ 工作流完成！")
    else:
        print("❌ 审核未通过，工作流暂停。状态已保存。")

    print(f"\n状态文件: {engine.state_file}")


if __name__ == "__main__":
    main()
