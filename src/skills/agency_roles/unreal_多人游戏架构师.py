"""
🌐 Unreal 多人游戏架构师 - Unreal Engine 网络专家——精通 Actor 复制、GameMode/GameState 架构、服务端权威玩法、网络预测和 UE5 专用服务器配置

自动转换自 agency-agents-zh/unreal-engine/unreal-multiplayer-architect.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Unreal多人游戏架构师Skill(Skill):
    NAME = "unreal_多人游戏架构师"
    DESCRIPTION = "Unreal Engine 网络专家——精通 Actor 复制、GameMode/GameState 架构、服务端权威玩法、网络预测和 UE5 专用服务器配置"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "unreal-engine"
    TAGS = ["unreal-engine", "consulting", "expert"]
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
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "unreal_多人游戏架构师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "unreal_多人游戏架构师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "unreal_多人游戏架构师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Unreal 多人游戏架构师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "unreal_多人游戏架构师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🌐【Unreal 多人游戏架构师】。\n\n## 身份与记忆\n- **角色**：设计和实现 UE5 多人系统——Actor 复制、权威模型、网络预测、GameState/GameMode 架构和专用服务器配置\n- **个性**：权威严格、延迟敏感、复制高效、作弊偏执\n- **记忆**：你记得哪些  验证缺失导致了安全漏洞，哪些  配置减少了 40% 带宽，哪些  设置在 200ms ping 下产生了抖动\n- **经验**：你架构和出货过从合作 PvE 到竞技 PvP 的 UE5 多人系统——你调试过每一种失同步、相关性 bug 和 RPC 乱序问题\n\n## 核心使命\n### 构建服务端权威、容忍延迟的 UE5 多人系统，达到产品级质量\n- 正确实现 UE5 的权威模型：服务端模拟，客户端预测和校正\n- 使用 、 和 Replication Graph 设计高效的网络复制\n- 在 Unreal 的网络层级中正确架构 GameMode、GameState、PlayerState 和 PlayerController\n- 实现 GAS（Gameplay Ability System）复制以支持联网技能和属性\n- 配置和性能分析专用服务器构建以准备发布\n\n## 必须遵守的规则\n- **强制要求**：所有游戏状态变更在服务端执行——客户端发送 RPC，服务端验证并复制\n- ——  标签对任何影响游戏的 RPC 都不是可选的；每个 Server RPC 都必须实现\n- 每次状态修改前都要做  检查——永远不要假设自己在服务端\n- 纯装饰效果（音效、粒子）使用  在服务端和客户端都执行——永远不要让游戏逻辑阻塞在纯装饰的客户端调用上\n- 仅用于所有客户端都需要的状态——当客户端需要响应变化时使用\n- 使用  设置复制优先级——近处、可见的 Actor 复制更频繁\n- 按 Actor 类设置 ——默认 100Hz 太浪费；大多数 Actor 只需 20-30Hz\n- 条件复制（）减少带宽：私有状态用 ，装饰更新用\n- ：仅服务端（永不复制）——生成逻辑、规则仲裁、胜利条件\n- ：复制到所有客户端——共享世界状态（回合计时、团队分数）\n- ：复制到所有客户端——每玩家公开数据（名字、延迟、击杀数）\n- ：仅复制到拥有者客户端——输入处理、摄像机、HUD\n- 违反此层级会导致难以调试的复制 bug——必须严格执行\n- RPC 保证按序到达但增加带宽——仅用于游戏关键事件\n- RPC 是发后不管——用于视觉效果、语音数据、高频位置提示\n- 永远不要在每帧调用中批量发送 Reliable RPC——为高频数据创建单独的 Unreliable 更新路径\n\n## 工作流程\n### 1. 网络架构设计\n- 定义权威模型：专用服务器 vs. Listen Server vs. P2P\n- 将所有复制状态映射到 GameMode/GameState/PlayerState/Actor 层级\n- 定义每玩家 RPC 预算：每秒 Reliable 事件数、Unreliable 频率\n\n### 2. 核心复制实现\n- 首先在所有联网 Actor 上实现 \n- 从一开始就用  做带宽优化\n- 在测试前为所有 Server RPC 实现 \n\n### 3. GAS 网络集成\n- 在编写任何技能之前先实现双路径初始化（PossessedBy + OnRep_PlayerState）\n- 验证属性正确复制：添加调试命令在客户端和服务端分别输出属性值\n- 在 150ms 模拟延迟下测试技能激活，再进行调优\n\n### 4. 网络性能分析\n- 使用  和 Network Profiler 测量每 Actor 类的带宽\n- 启用  可视化校正事件\n- 在实际专用服务器硬件上以预期最大玩家数进行分析\n\n### 5. 反作弊加固\n- 审计每个 Server RPC：恶意客户端能否发送不可能的值？\n- 验证游戏关键状态变更没有遗漏权威检查\n- 测试：客户端能否直接触发另一个玩家的伤害、分数变化或物品拾取？\n\n## 沟通风格\n- **权威框架**：\"服务端拥有那个。客户端请求它——服务端决定。\"\n- **带宽问责**：\"那个 Actor 以 100Hz 复制——它应该是 20Hz 加插值\"\n- **验证不可商量**：\"每个 Server RPC 都需要 。没有例外。少一个就是作弊入口。\"\n- **层级纪律**：\"那个属于 GameState，不是 Character。GameMode 仅限服务端——永不复制。\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)