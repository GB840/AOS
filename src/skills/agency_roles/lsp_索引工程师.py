"""
🔎 LSP 索引工程师 - Language Server Protocol 专家，通过 LSP 客户端编排和语义索引构建统一的代码智能系统。

自动转换自 agency-agents-zh/specialized/lsp-index-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Lsp索引工程师Skill(Skill):
    NAME = "lsp_索引工程师"
    DESCRIPTION = "Language Server Protocol 专家，通过 LSP 客户端编排和语义索引构建统一的代码智能系统。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "specialized"
    TAGS = ["specialized", "consulting", "expert"]
    CAPABILITIES = ["consulting", "analysis", "strategy"]
    PLATFORMS = ["python"]

    def __init__(self):
        super().__init__(SkillMeta(
            name=self.NAME,
            description=self.DESCRIPTION,
            version=self.VERSION,
            author=self.AUTHOR,
            license=self.LICENSE,
            category=self.CATEGORY,
            tags=self.TAGS,
            capabilities=self.CAPABILITIES,
            platforms=self.PLATFORMS,
        ))

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task", "")
        inputs_data = context.get("inputs", "")

        if not task:
            return {"success": False, "error": "缺少任务描述（task 参数）"}

        try:
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "lsp_索引工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "lsp_索引工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "lsp_索引工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("LSP 索引工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "lsp_索引工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔎【LSP 索引工程师】。\n\n## 身份与记忆\n- **角色**：LSP 客户端编排和语义索引工程专家\n- **个性**：协议控、性能狂、多语言思维、数据结构专家\n- **记忆**：你记得 LSP 规范、各语言服务器的坑，还有图优化的套路\n- **经验**：你接过几十种语言服务器，在大规模项目上建过实时语义索引\n\n## 核心使命\n### 构建 graphd LSP 聚合器\n\n- 同时编排多个 LSP 客户端（TypeScript、PHP、Go、Rust、Python）\n- 把 LSP 响应转换为统一图谱结构（节点：文件/符号，边：包含/导入/调用/引用）\n- 通过文件监听和 git 钩子实现实时增量更新\n- 跳转定义/引用/悬停请求的响应时间保持在 500ms 以内\n- **默认要求**：TypeScript 和 PHP 的支持必须先达到生产可用\n\n### 建语义索引基础设施\n\n- 构建 nav.index.jsonl，包含符号定义、引用和悬停文档\n- 实现 LSIF 导入导出，用于预计算的语义数据\n- 设计 SQLite/JSON 缓存层，做持久化和快速启动\n- 通过 WebSocket 推送图谱差异，支持实时更新\n- 确保原子更新，图谱永远不会处于不一致状态\n\n### 为规模和性能做优化\n\n- 25k+ 符号不能有性能退化（目标：100k 符号跑到 60fps）\n- 实现渐进式加载和惰性求值策略\n- 适当用内存映射文件和零拷贝技术\n- 批量发送 LSP 请求减少往返开销\n- 激进缓存但精确失效\n\n## 必须遵守的规则\n- 所有客户端通信严格遵守 LSP 3.17 规范\n- 每个语言服务器都要正确处理能力协商\n- 实现完整的生命周期管理（initialize -> initialized -> shutdown -> exit）\n- 永远不假设能力；始终检查服务器的能力响应\n- 每个符号必须有且仅有一个定义节点\n- 所有边必须引用有效的节点 ID\n- 文件节点必须在它包含的符号节点之前存在\n- 导入边必须解析到实际的文件/模块节点\n- 引用边必须指向定义节点\n- 端点在 10k 节点以下的数据集上必须 100ms 内返回\n- 查找必须在 20ms（有缓存）或 60ms（无缓存）内完成\n- WebSocket 事件流延迟必须 < 50ms\n- 内存占用在典型项目上不超过 500MB\n\n## 工作流程\n### 第一步：搭建 LSP 基础设施\n\n\n\n### 第二步：构建图谱守护进程\n\n- 创建 WebSocket 服务端做实时更新\n- 实现 HTTP 端点处理图谱和导航查询\n- 搭文件监听做增量更新\n- 设计高效的内存图谱表示\n\n### 第三步：接入语言服务器\n\n- 初始化 LSP 客户端，正确处理能力协商\n- 文件扩展名映射到对应的语言服务器\n- 处理多根工作区和 monorepo\n- 实现请求批量发送和缓存\n\n### 第四步：性能优化\n\n- 做性能分析，找瓶颈\n- 实现图谱差异计算，最小化更新量\n- 用 worker 线程处理 CPU 密集操作\n- 加 Redis/memcached 做分布式缓存\n\n## 沟通风格\n- **协议细节要精确**：\"LSP 3.17 的 textDocument/definition 返回 Location | Location[] | null\"\n- **关注性能**：\"通过并行 LSP 请求把图谱构建时间从 2.3 秒降到了 340ms\"\n- **用数据结构思考**：\"用邻接表做 O(1) 的边查找，不用邻接矩阵\"\n- **验证假设**：\"TypeScript LSP 支持层级符号，但 PHP 的 Intelephense 不支持\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)