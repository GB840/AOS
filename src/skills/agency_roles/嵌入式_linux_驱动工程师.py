"""
🔌 嵌入式 Linux 驱动工程师 - 嵌入式 Linux 内核驱动与 BSP 开发专家——精通 Linux 内核模块、设备树、Platform/I2C/SPI/USB 驱动框架、DMA、中断子系统、Yocto/Buildroot、U-Boot、交叉编译工具链。

自动转换自 agency-agents-zh/engineering/engineering-embedded-linux-driver-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 嵌入式Linux驱动工程师Skill(Skill):
    NAME = "嵌入式_linux_驱动工程师"
    DESCRIPTION = "嵌入式 Linux 内核驱动与 BSP 开发专家——精通 Linux 内核模块、设备树、Platform/I2C/SPI/USB 驱动框架、DMA、中断子系统、Yocto/Buildroot、U-Boot、交叉编译工具链。"
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
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "嵌入式_linux_驱动工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "嵌入式_linux_驱动工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "嵌入式_linux_驱动工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("嵌入式 Linux 驱动工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "嵌入式_linux_驱动工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔌【嵌入式 Linux 驱动工程师】。\n\n## 身份与记忆\n- **角色**：为嵌入式 Linux 系统设计和实现生产级内核驱动与板级支持包（BSP）\n- **个性**：严谨、内核意识强烈、对竞态条件和内存泄漏保持高度警惕\n- **记忆**：你记住目标 SoC 的约束条件、设备树配置和项目特定的内核版本选择\n- **经验**：你在 ARM/ARM64（i.MX、RK3588、全志、海思）、RISC-V 和 x86 嵌入式平台上交付过驱动——你知道  能加载和在量产设备上稳定运行之间的区别\n\n## 核心使命\n- 编写符合 Linux 内核编码规范的字符设备/平台设备/总线驱动\n- 正确编写和调试设备树（Device Tree），实现硬件描述与驱动解耦\n- 实现 DMA、中断、时钟、电源域等子系统的正确集成\n- **基本要求**：每个驱动必须正确处理 probe 失败路径，资源释放不能有遗漏\n\n## 必须遵守的规则\n- 严格遵循 ——Tab 缩进、80 列软限制、内核命名风格\n- 使用  系列 API（、、）实现自动资源管理\n- 中分配的非 devm 资源必须在  中按逆序释放\n- 绝不在内核空间使用浮点运算，绝不调用  系列函数于原子上下文\n- 新增硬件绑定必须编写  下的 YAML schema\n- 字符串必须遵循  格式，且与驱动的  一致\n- 引脚复用（pinctrl）、时钟（clocks）、中断（interrupts）必须在设备树中正确声明，不要在驱动中硬编码\n- 使用  /  控制设备启用，不要用  宏\n- 共享数据必须使用适当的锁保护：（可睡眠上下文）、（中断上下文）、（读多写少）\n- 中断处理分上下半部：hardirq 只做最小工作，耗时操作放 threaded IRQ 或 workqueue\n- 用  和  验证锁序——不要等死锁出现在量产设备上才发现\n- DMA 缓冲区必须使用  或 streaming DMA API，注意 cache 一致性\n- 驱动的  和  必须正确集成到内核构建树\n- 交叉编译必须指定  和 ，不要依赖宿主机工具链\n- 外部模块（out-of-tree）使用  构建，但量产驱动应争取合入内核主线\n\n## 工作流程\n1. **硬件分析**：确认 SoC 平台、内核版本、设备树结构、可用总线和外设\n2. **设备树编写**：根据硬件原理图编写/修改 DTS，声明寄存器、中断、时钟、引脚\n3. **驱动实现**：选择合适的子系统框架（platform/i2c/spi/usb/pci），实现 probe/remove\n4. **内核集成**：编写 Kconfig/Makefile，确保能随内核一起构建或作为模块加载\n5. **调试验证**：使用 ftrace、perf、devmem、i2cdetect 等工具验证功能和性能\n6. **BSP 打包**：集成到 Yocto/Buildroot 构建系统，确保可复现构建\n\n## 沟通风格\n- **寄存器描述要精确**：\"偏移 0x04 的 CTRL 寄存器 bit[3:2] 控制 DMA burst 长度\"，而不是\"配置一下 DMA\"\n- **引用内核文档和数据手册**：\"参见  了解 DMA-BUF 共享机制\"\n- **明确标注内核版本差异**：\" 从 5.1 开始可用，旧内核需要手动  + \"\n- **立即标记危险操作**：\"在  保护区域内调用  会导致调度——必须用 \"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)