# AOS 文档分析报告

**目标目录**: `D:\AOS\src\kernel`
**分析时间**: 2026-07-11 23:53:34
**使用模型**: deeproute:gpt-4o-mini
**耗时**: 0.12s

## 项目总结

共 31 个文件，17059 词，6095 行。文件类型分布: 31个python。发现 237 个关键洞察。洞察分类: 237个dependency。

## 改进建议

- 31 个文件缺少清晰的文档结构，建议添加标题和章节划分

## 关键洞察 (237)

### D:\AOS\src\kernel\auth_bridge.py
- 🟡 **[dependency]** 外部依赖: 导入: - 零依赖：本模块只依赖 kernel types，不 import api/security 或 FastAPI
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Callable, Dict, List, Optional
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.types import Permission
- 🟡 **[dependency]** 外部依赖: 导入: import base64
- 🟡 **[dependency]** 外部依赖: 导入: import base64
- 🟡 **[dependency]** 外部依赖: 导入: import hashlib
- 🟡 **[dependency]** 外部依赖: 导入: import hmac
- 🟡 **[dependency]** 外部依赖: 导入: import json
- 🟡 **[dependency]** 外部依赖: 导入: import os
- 🟡 **[dependency]** 外部依赖: 导入: "开发: export AOS_TOKEN_SECRET=$(python -c 'import secrets; print(secrets.token_he
- 🟡 **[dependency]** 外部依赖: 导入: import base64
- 🟡 **[dependency]** 外部依赖: 导入: import hashlib
- 🟡 **[dependency]** 外部依赖: 导入: import hmac
- 🟡 **[dependency]** 外部依赖: 导入: import json
- 🟡 **[dependency]** 外部依赖: 导入: import os

### D:\AOS\src\kernel\v5_bridge.py
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.v5_bridge import V5Bridge
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: import os
- 🟡 **[dependency]** 外部依赖: 导入: import time
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Callable, Dict, List, Optional
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.system import build_default_system, AOSSystem
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.types import AgentSpec, Message, Response
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.auth_bridge import AuthBridge, AuthProvider
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.skills_bridge import SkillsBridge
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.compliance import ComplianceLayer
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.evolution import FitnessTracker
- 🟡 **[dependency]** 外部依赖: 导入: from dotenv import load_dotenv
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.v5_bridge import get_bridge
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.interfaces import AgentRuntime

### D:\AOS\src\kernel\layers\agent_runtime_layer.py
- 🟡 **[dependency]** 外部依赖: 导入: 依赖倒置：本层依赖 AgentRuntime ABC + AOSKernel + stdlib，不 import 具体引擎。
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: import asyncio
- 🟡 **[dependency]** 外部依赖: 导入: from abc import ABC, abstractmethod
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List, Optional
- 🟡 **[dependency]** 外部依赖: 导入: from ..interfaces import AgentRuntime
- 🟡 **[dependency]** 外部依赖: 导入: from ..kernel import AOSKernel
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import AgentInstance, AgentSpec, AgentStatus, Response
- 🟡 **[dependency]** 外部依赖: 导入: import json
- 🟡 **[dependency]** 外部依赖: 导入: import os
- 🟡 **[dependency]** 外部依赖: 导入: import json
- 🟡 **[dependency]** 外部依赖: 导入: import os
- 🟡 **[dependency]** 外部依赖: 导入: import time

### D:\AOS\src\kernel\__init__.py
- 🟡 **[dependency]** 外部依赖: 导入: from .auth_bridge import AuthBridge, AuthProvider, AuthResult
- 🟡 **[dependency]** 外部依赖: 导入: from .compliance import AuditEntry, AuditTrail, ComplianceLayer, ContentGuard, P
- 🟡 **[dependency]** 外部依赖: 导入: from .ecology import NaturalSelection, ResourceBudget, ResourceEconomy, Symbiosi
- 🟡 **[dependency]** 外部依赖: 导入: from .events import Event, EventBus, EventEmitter, SystemEvent
- 🟡 **[dependency]** 外部依赖: 导入: from .evolution import AgentDNA, Breeder, FitnessScore, FitnessTracker, Gene
- 🟡 **[dependency]** 外部依赖: 导入: from .future import ComplianceLayer, ModelCapabilityExt, ModelCapabilityProvider
- 🟡 **[dependency]** 外部依赖: 导入: from .hippo_scroll import (
- 🟡 **[dependency]** 外部依赖: 导入: from .hotswap import HotSwapManager
- 🟡 **[dependency]** 外部依赖: 导入: from .immunity import AnomalyDetector, CircuitBreaker, CircuitBreakerOpenError, 
- 🟡 **[dependency]** 外部依赖: 导入: from .interfaces import AgentRuntime, ModelGateway, SkillBus
- 🟡 **[dependency]** 外部依赖: 导入: from .kernel import AOSKernel
- 🟡 **[dependency]** 外部依赖: 导入: from .types import (
- 🟡 **[dependency]** 外部依赖: 导入: from .versioning import (

### D:\AOS\src\kernel\live.py
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.live import LiveEvolutionEngine
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: import time
- 🟡 **[dependency]** 外部依赖: 导入: import threading
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List, Optional
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.system import build_default_system, AOSSystem
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.types import AgentSpec, Message, Response
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.evolution import AgentDNA, Gene, FitnessTracker, Breeder
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.ecology import NaturalSelection, ResourceEconomy
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.immunity import AnomalyDetector, SelfHealer
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.events import Event

### D:\AOS\src\kernel\skills_bridge.py
- 🟡 **[dependency]** 外部依赖: 导入: - 零依赖：本模块只依赖 kernel ABCs，import skills 是延迟的（只在 register_all 时）
- 🟡 **[dependency]** 外部依赖: 导入: - 向后兼容：skill 内部 import get_brain 等不受影响，本桥接只是多一条注册通道
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.interfaces import SkillBus
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.types import SkillResult, SkillSpec
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.wiring import build_default_kernel
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.skills_bridge import SkillsBridge
- 🟡 **[dependency]** 外部依赖: 导入: import importlib
- 🟡 **[dependency]** 外部依赖: 导入: import pkgutil
- 🟡 **[dependency]** 外部依赖: 导入: import skills as skills_pkg  # 延迟导入
- 🟡 **[dependency]** 外部依赖: 导入: import importlib

### D:\AOS\src\kernel\wiring.py
- 🟡 **[dependency]** 外部依赖: 导入: 核心零依赖；本文件才 import 具体实现，且对每个插件用 try/except 包裹，
- 🟡 **[dependency]** 外部依赖: 导入: 调用方：app 启动 / 测试 / CLI 引导时 `from kernel.wiring import build_default_kernel`。
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from .kernel import AOSKernel
- 🟡 **[dependency]** 外部依赖: 导入: from .plugins import FabricAgentRuntime, LiteLLMModelGateway, MCPSkillBus
- 🟡 **[dependency]** 外部依赖: 导入: import importlib
- 🟡 **[dependency]** 外部依赖: 导入: from .plugins.mistralrs_gateway import MistralRSModelGateway
- 🟡 **[dependency]** 外部依赖: 导入: from .plugins.composite_gateway import CompositeModelGateway
- 🟡 **[dependency]** 外部依赖: 导入: from core.fabric.adapters.litellm_adapter import LiteLLMAdapter

### D:\AOS\src\kernel\compliance.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: import hashlib
- 🟡 **[dependency]** 外部依赖: 导入: import json
- 🟡 **[dependency]** 外部依赖: 导入: import re
- 🟡 **[dependency]** 外部依赖: 导入: import threading
- 🟡 **[dependency]** 外部依赖: 导入: import time
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple

### D:\AOS\src\kernel\immunity.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: import threading
- 🟡 **[dependency]** 外部依赖: 导入: import time
- 🟡 **[dependency]** 外部依赖: 导入: from collections import defaultdict
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Callable, Dict, List
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.events import Event, EventBus, SystemEvent
- 🟡 **[dependency]** 外部依赖: 导入: import datetime

### D:\AOS\src\kernel\kernel.py
- 🟡 **[dependency]** 外部依赖: 导入: 内核本身零依赖：本文件只 import 标准库 + 同包的 .types / .interfaces。
- 🟡 **[dependency]** 外部依赖: 导入: 绝不 import brain / litellm / mcp / fabric —— 那些是"插件"，由外部接线层登记进来。
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Callable, Dict, List, Optional
- 🟡 **[dependency]** 外部依赖: 导入: from .interfaces import AgentRuntime, ModelGateway, SkillBus
- 🟡 **[dependency]** 外部依赖: 导入: from .types import (
- 🟡 **[dependency]** 外部依赖: 导入: from .events import EventBus
- 🟡 **[dependency]** 外部依赖: 导入: from .events import Event

### D:\AOS\src\kernel\system.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Dict
- 🟡 **[dependency]** 外部依赖: 导入: from .kernel import AOSKernel
- 🟡 **[dependency]** 外部依赖: 导入: from .layers import (
- 🟡 **[dependency]** 外部依赖: 导入: from .wiring import build_default_kernel
- 🟡 **[dependency]** 外部依赖: 导入: from .types import AgentSpec
- 🟡 **[dependency]** 外部依赖: 导入: from .immunity import SelfHealer

### D:\AOS\src\kernel\plugins\litellm_gateway.py
- 🟡 **[dependency]** 外部依赖: 导入: 挂入，内核一行不改。内核零依赖，本文件才允许 import 具体实现。
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, AsyncIterator, Dict, List
- 🟡 **[dependency]** 外部依赖: 导入: from ..interfaces import ModelGateway
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import (
- 🟡 **[dependency]** 外部依赖: 导入: from core.fabric.adapters.litellm_adapter import LiteLLMAdapter
- 🟡 **[dependency]** 外部依赖: 导入: from core.fabric.adapter import InvokeRequest
- 🟡 **[dependency]** 外部依赖: 导入: from core.fabric.capability import Capability

### D:\AOS\src\kernel\ecology.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: import threading
- 🟡 **[dependency]** 外部依赖: 导入: import time
- 🟡 **[dependency]** 外部依赖: 导入: from collections import defaultdict
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Callable, Dict, List, Optional, Set, Tuple
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.evolution import FitnessTracker

### D:\AOS\src\kernel\hippo_scroll.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: import hashlib
- 🟡 **[dependency]** 外部依赖: 导入: import threading
- 🟡 **[dependency]** 外部依赖: 导入: import time
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from enum import Enum
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Callable, Dict, List, Optional, Tuple

### D:\AOS\src\kernel\layers\mcp_bus_layer.py
- 🟡 **[dependency]** 外部依赖: 导入: 依赖倒置：本层依赖 SkillBus ABC + AOSKernel，不 import 任何具体协议实现。
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List
- 🟡 **[dependency]** 外部依赖: 导入: from ..interfaces import SkillBus
- 🟡 **[dependency]** 外部依赖: 导入: from ..kernel import AOSKernel
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import SkillInfo, SkillResult, SkillSpec
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import Permission

### D:\AOS\src\kernel\layers\model_gateway_layer.py
- 🟡 **[dependency]** 外部依赖: 导入: 依赖倒置：本层只依赖 ModelGateway ABC + stdlib，不 import 任何具体模型引擎。
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List, Optional
- 🟡 **[dependency]** 外部依赖: 导入: import threading
- 🟡 **[dependency]** 外部依赖: 导入: from ..interfaces import ModelGateway
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import ChatResponse, Message, ModelInfo

### D:\AOS\src\kernel\plugins\fabric_runtime.py
- 🟡 **[dependency]** 外部依赖: 导入: 才允许 import 具体实现（core.fabric）。
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, AsyncIterator
- 🟡 **[dependency]** 外部依赖: 导入: from ..interfaces import AgentRuntime
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import AgentInstance, AgentSpec, Response
- 🟡 **[dependency]** 外部依赖: 导入: from core.fabric.adapter import BaseAgentAdapter, InvokeRequest
- 🟡 **[dependency]** 外部依赖: 导入: from core.fabric.capability import Capability

### D:\AOS\src\kernel\plugins\mistralrs_gateway.py
- 🟡 **[dependency]** 外部依赖: 导入: 内核核心零依赖；本文件位于 plugins/，允许 import 具体实现（openai / config）。
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, AsyncIterator, Dict, List
- 🟡 **[dependency]** 外部依赖: 导入: from ..interfaces import ModelGateway
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import (
- 🟡 **[dependency]** 外部依赖: 导入: from openai import OpenAI
- 🟡 **[dependency]** 外部依赖: 导入: from utils.config import config as _cfg

### D:\AOS\src\kernel\events.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from threading import Lock
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Callable, Dict, List, Optional
- 🟡 **[dependency]** 外部依赖: 导入: import datetime
- 🟡 **[dependency]** 外部依赖: 导入: import threading

### D:\AOS\src\kernel\evolution.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: import random
- 🟡 **[dependency]** 外部依赖: 导入: from copy import deepcopy
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List, Optional
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.types import AgentSpec

### D:\AOS\src\kernel\hotswap.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from threading import Lock
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.events import Event, SystemEvent
- 🟡 **[dependency]** 外部依赖: 导入: from kernel.interfaces import AgentRuntime, ModelGateway, SkillBus
- 🟡 **[dependency]** 外部依赖: 导入: import datetime

### D:\AOS\src\kernel\layers\model_fallback.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Callable, Dict, List, Optional
- 🟡 **[dependency]** 外部依赖: 导入: from ..interfaces import ModelGateway
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import ChatResponse, Message
- 🟡 **[dependency]** 外部依赖: 导入: import asyncio

### D:\AOS\src\kernel\layers\__init__.py
- 🟡 **[dependency]** 外部依赖: 导入: 每个层级只依赖 kernel ABCs + stdlib，不 import 具体实现。
- 🟡 **[dependency]** 外部依赖: 导入: from .agent_runtime_layer import (
- 🟡 **[dependency]** 外部依赖: 导入: from .mcp_bus_layer import MCPBusLayer
- 🟡 **[dependency]** 外部依赖: 导入: from .model_fallback import FallbackChain, FallbackResult
- 🟡 **[dependency]** 外部依赖: 导入: from .model_gateway_layer import CostTracker, ModelGatewayLayer, RouteStrategy
- 🟡 **[dependency]** 外部依赖: 导入: from .ui_layer import CLIUILayer, SurfaceKind, UILayer, UIRender, UISurface, Web

### D:\AOS\src\kernel\plugins\mcp_skill_bus.py
- 🟡 **[dependency]** 外部依赖: 导入: 内核零依赖，本文件才允许 import 具体实现（mcp.protocol）。
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List
- 🟡 **[dependency]** 外部依赖: 导入: from ..interfaces import SkillBus
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import SkillInfo, SkillResult, SkillSpec
- 🟡 **[dependency]** 外部依赖: 导入: from mcp.protocol import MCPProtocol, MCPTool

### D:\AOS\src\kernel\types.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from datetime import datetime, timezone
- 🟡 **[dependency]** 外部依赖: 导入: from enum import Enum
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List, Optional

### D:\AOS\src\kernel\future.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from abc import ABC, abstractmethod
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, AsyncIterator, Dict, List

### D:\AOS\src\kernel\interfaces.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from abc import ABC, abstractmethod
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, AsyncIterator, Dict, List
- 🟡 **[dependency]** 外部依赖: 导入: from .types import (

### D:\AOS\src\kernel\layers\ui_layer.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from abc import ABC, abstractmethod
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Dict, List, Optional

### D:\AOS\src\kernel\plugins\composite_gateway.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, AsyncIterator, List
- 🟡 **[dependency]** 外部依赖: 导入: from ..interfaces import ModelGateway
- 🟡 **[dependency]** 外部依赖: 导入: from ..types import ChatChunk, ChatResponse, Message, ModelCapabilities, ModelIn

### D:\AOS\src\kernel\plugins\__init__.py
- 🟡 **[dependency]** 外部依赖: 导入: 零依赖；本包才允许 import 具体实现（core.fabric / mcp / litellm）。
- 🟡 **[dependency]** 外部依赖: 导入: from .fabric_runtime import FabricAgentRuntime
- 🟡 **[dependency]** 外部依赖: 导入: from .litellm_gateway import LiteLLMModelGateway
- 🟡 **[dependency]** 外部依赖: 导入: from .mcp_skill_bus import MCPSkillBus

### D:\AOS\src\kernel\versioning.py
- 🟡 **[dependency]** 外部依赖: 导入: from __future__ import annotations
- 🟡 **[dependency]** 外部依赖: 导入: from dataclasses import dataclass, field
- 🟡 **[dependency]** 外部依赖: 导入: from typing import Any, Callable, Dict, List, Optional

## 文件概览 (31)

| 文件 | 类型 | 词数 | 行数 | 章节 | 结构 | 可读性 |
|------|------|------|------|------|------|--------|
| auth_bridge.py | python | 674 | 229 | 0 | ███░░░░░░░ | ██████░░░░ |
| compliance.py | python | 1378 | 491 | 0 | ███░░░░░░░ | ██████░░░░ |
| ecology.py | python | 750 | 255 | 0 | ███░░░░░░░ | ██████░░░░ |
| events.py | python | 570 | 239 | 0 | ███░░░░░░░ | ██████░░░░ |
| evolution.py | python | 1041 | 342 | 0 | ███░░░░░░░ | ██████░░░░ |
| future.py | python | 289 | 130 | 0 | ███░░░░░░░ | ██████░░░░ |
| hippo_scroll.py | python | 1808 | 634 | 0 | ███░░░░░░░ | ██████░░░░ |
| hotswap.py | python | 291 | 115 | 0 | ███░░░░░░░ | ██████░░░░ |
| immunity.py | python | 822 | 296 | 0 | ███░░░░░░░ | ██████░░░░ |
| interfaces.py | python | 229 | 104 | 0 | ███░░░░░░░ | ██████░░░░ |
| kernel.py | python | 489 | 169 | 0 | ███░░░░░░░ | ██████░░░░ |
| live.py | python | 948 | 341 | 0 | ███░░░░░░░ | ██████░░░░ |
| skills_bridge.py | python | 451 | 165 | 0 | ███░░░░░░░ | ██████░░░░ |
| system.py | python | 496 | 168 | 0 | ███░░░░░░░ | ██████░░░░ |
| types.py | python | 324 | 159 | 0 | ███░░░░░░░ | ██████░░░░ |
| v5_bridge.py | python | 913 | 328 | 0 | ███░░░░░░░ | ██████░░░░ |
| versioning.py | python | 685 | 244 | 0 | ███░░░░░░░ | ██████░░░░ |
| wiring.py | python | 305 | 101 | 0 | ███░░░░░░░ | ██████░░░░ |
| __init__.py | python | 217 | 85 | 0 | ███░░░░░░░ | ██████░░░░ |
| agent_runtime_layer.py | python | 901 | 314 | 0 | ███░░░░░░░ | ██████░░░░ |
| mcp_bus_layer.py | python | 311 | 104 | 0 | ███░░░░░░░ | ██████░░░░ |
| model_fallback.py | python | 457 | 160 | 0 | ███░░░░░░░ | ██████░░░░ |
| model_gateway_layer.py | python | 711 | 229 | 0 | ███░░░░░░░ | ██████░░░░ |
| ui_layer.py | python | 466 | 170 | 0 | ███░░░░░░░ | ██████░░░░ |
| __init__.py | python | 106 | 44 | 0 | ███░░░░░░░ | ██████░░░░ |
| composite_gateway.py | python | 285 | 93 | 0 | ███░░░░░░░ | ██████░░░░ |
| fabric_runtime.py | python | 236 | 79 | 0 | ███░░░░░░░ | ██████░░░░ |
| litellm_gateway.py | python | 220 | 84 | 0 | ███░░░░░░░ | ██████░░░░ |
| mcp_skill_bus.py | python | 147 | 52 | 0 | ███░░░░░░░ | ██████░░░░ |
| mistralrs_gateway.py | python | 484 | 151 | 0 | ███░░░░░░░ | ██████░░░░ |
| __init__.py | python | 55 | 20 | 0 | ███░░░░░░░ | ██████░░░░ |

## 组件清单

| 组件 | 来源 | 用途 |
|------|------|------|
| LLM 推理 | deeproute:gpt-4o-mini | 文档深度分析 |
| WorkspaceManager | `src/execution/workspace.py` | 文件读写操作 |
| ThreadPoolExecutor | `concurrent.futures` | 多文件并行分析 |
| 分析 Prompt | `src/capabilities/doc_analysis.py` | 分析规则定义 |
| 文件分类器 | `src/capabilities/doc_analysis.py` | 自动识别文件类型 |

---
*由 AOS Document Analysis Pipeline 生成*