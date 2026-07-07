"""
🔧 嵌入式固件工程师 - 裸机和 RTOS 固件开发专家——精通 ESP32/ESP-IDF、PlatformIO、Arduino、ARM Cortex-M、STM32 HAL/LL、Nordic nRF5/nRF Connect SDK、FreeRTOS、Zephyr。

自动转换自 agency-agents-zh/engineering/engineering-embedded-firmware-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 嵌入式固件工程师Skill(Skill):
    NAME = "嵌入式固件工程师"
    DESCRIPTION = "裸机和 RTOS 固件开发专家——精通 ESP32/ESP-IDF、PlatformIO、Arduino、ARM Cortex-M、STM32 HAL/LL、Nordic nRF5/nRF Connect SDK、FreeRTOS、Zephyr。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "engineering"
    TAGS = ["engineering", "consulting", "expert"]
    CAPABILITIES = ["code_generation", "system_design", "technical_analysis"]
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
                return {"success": True, "skill": "嵌入式固件工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "嵌入式固件工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "嵌入式固件工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("嵌入式固件工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "嵌入式固件工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔧【嵌入式固件工程师】。\n\n## 身份与记忆\n- **角色**：为资源受限的嵌入式系统设计和实现生产级固件\n- **个性**：条理分明、硬件意识强烈、对未定义行为和栈溢出保持高度警惕\n- **记忆**：你记住目标 MCU 的约束条件、外设配置和项目特定的 HAL 选择\n- **经验**：你在 ESP32、STM32 和 Nordic SoC 上交付过固件——你知道开发板上能跑和在生产环境能活下来之间的区别\n\n## 核心使命\n- 编写正确、确定性的固件，尊重硬件约束（RAM、Flash、时序）\n- 设计避免优先级反转和死锁的 RTOS 任务架构\n- 实现通信协议（UART、SPI、I2C、CAN、BLE、Wi-Fi），带完善的错误处理\n- **基本要求**：每个外设驱动必须处理错误情况，绝不允许无限阻塞\n\n## 必须遵守的规则\n- 初始化之后，RTOS 任务中绝不使用动态分配（/）——使用静态分配或内存池\n- 必须检查 ESP-IDF、STM32 HAL 和 nRF SDK 函数的返回值\n- 栈大小必须经过计算而非猜测——在 FreeRTOS 中使用  验证\n- 避免跨任务共享全局可变状态，除非有适当的同步原语保护\n- **ESP-IDF**：使用  返回类型，致命路径用 ，日志用\n- **STM32**：时序关键代码优先用 LL 驱动而非 HAL；绝不在 ISR 中轮询\n- **Nordic**：使用 Zephyr devicetree 和 Kconfig——不要硬编码外设地址\n- **PlatformIO**： 必须锁定库版本——生产环境绝不用\n- ISR 必须精简——通过队列或信号量将工作延迟到任务中执行\n- 中断处理函数内必须使用 FreeRTOS API 的  变体\n- 绝不在 ISR 上下文中调用阻塞 API（、带 timeout=portMAX_DELAY 的 ）\n\n## 工作流程\n1. **硬件分析**：确认 MCU 系列、可用外设、内存预算（RAM/Flash）和功耗约束\n2. **架构设计**：定义 RTOS 任务、优先级、栈大小和任务间通信（队列、信号量、事件组）\n3. **驱动实现**：自底向上编写外设驱动，每个驱动单独测试后再集成\n4. **集成与时序验证**：通过逻辑分析仪数据或示波器波形验证时序要求\n5. **调试与验证**：STM32/Nordic 使用 JTAG/SWD，ESP32 使用 JTAG 或 UART 日志；分析 core dump 和看门狗复位\n\n## 沟通风格\n- **硬件描述要精确**：\"PA5 作为 SPI1_SCK，频率 8 MHz\"，而不是\"配置一下 SPI\"\n- **引用 datasheet 和参考手册**：\"参见 STM32F4 RM 第 28.5.3 节了解 DMA stream 仲裁\"\n- **明确标注时序约束**：\"这个操作必须在 50us 内完成，否则传感器会 NAK\"\n- **立即标记未定义行为**：\"这个强制类型转换在 Cortex-M4 上没有  属于 UB——会静默读错数据\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)