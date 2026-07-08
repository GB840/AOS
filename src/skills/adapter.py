from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import logging
from .base import Skill, SkillMeta

logger = logging.getLogger(__name__)

class TargetEnvironment(Enum):
    OLLAMA = "ollama"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    GPT_4 = "gpt_4"
    WENXIN = "wenxin"
    TONGYI = "tongyi"
    GLM = "glm"

class PromptStyle(Enum):
    SYSTEM_ONLY = "system_only"
    SYSTEM_USER = "system_user"
    INSTRUCTION_ONLY = "instruction_only"
    CONVERSATION = "conversation"
    XML_TAGGED = "xml_tagged"
    MARKDOWN = "markdown"

class ToolCallFormat(Enum):
    JSON = "json"
    XML = "xml"
    FUNCTION_CALL = "function_call"
    NATURAL_LANGUAGE = "natural_language"
    MARKDOWN_CODE_BLOCK = "markdown_code_block"

class SkillAdapter:
    def __init__(self, target_env: TargetEnvironment):
        self.target_env = target_env
        self.prompt_style = self._get_prompt_style(target_env)
        self.tool_format = self._get_tool_format(target_env)
        self.context_limit = self._get_context_limit(target_env)
        self.max_tokens = self._get_max_tokens(target_env)
    
    def _get_prompt_style(self, env: TargetEnvironment) -> PromptStyle:
        style_map = {
            TargetEnvironment.OLLAMA: PromptStyle.SYSTEM_USER,
            TargetEnvironment.CLAUDE_CODE: PromptStyle.SYSTEM_USER,
            TargetEnvironment.CODEX: PromptStyle.INSTRUCTION_ONLY,
            TargetEnvironment.GPT_4: PromptStyle.SYSTEM_USER,
            TargetEnvironment.WENXIN: PromptStyle.SYSTEM_USER,
            TargetEnvironment.TONGYI: PromptStyle.SYSTEM_USER,
            TargetEnvironment.GLM: PromptStyle.SYSTEM_USER,
        }
        return style_map.get(env, PromptStyle.SYSTEM_USER)
    
    def _get_tool_format(self, env: TargetEnvironment) -> ToolCallFormat:
        format_map = {
            TargetEnvironment.OLLAMA: ToolCallFormat.JSON,
            TargetEnvironment.CLAUDE_CODE: ToolCallFormat.XML,
            TargetEnvironment.CODEX: ToolCallFormat.FUNCTION_CALL,
            TargetEnvironment.GPT_4: ToolCallFormat.FUNCTION_CALL,
            TargetEnvironment.WENXIN: ToolCallFormat.JSON,
            TargetEnvironment.TONGYI: ToolCallFormat.FUNCTION_CALL,
            TargetEnvironment.GLM: ToolCallFormat.JSON,
        }
        return format_map.get(env, ToolCallFormat.JSON)
    
    def _get_context_limit(self, env: TargetEnvironment) -> int:
        limit_map = {
            TargetEnvironment.OLLAMA: 32768,
            TargetEnvironment.CLAUDE_CODE: 200000,
            TargetEnvironment.CODEX: 16384,
            TargetEnvironment.GPT_4: 128000,
            TargetEnvironment.WENXIN: 20000,
            TargetEnvironment.TONGYI: 32768,
            TargetEnvironment.GLM: 200000,
        }
        return limit_map.get(env, 32768)
    
    def _get_max_tokens(self, env: TargetEnvironment) -> int:
        token_map = {
            TargetEnvironment.OLLAMA: 8192,
            TargetEnvironment.CLAUDE_CODE: 8192,
            TargetEnvironment.CODEX: 4096,
            TargetEnvironment.GPT_4: 4096,
            TargetEnvironment.WENXIN: 4096,
            TargetEnvironment.TONGYI: 8192,
            TargetEnvironment.GLM: 8192,
        }
        return token_map.get(env, 4096)
    
    def adapt_prompt(self, skill: Skill, context: Dict[str, Any]) -> Dict[str, Any]:
        messages = []
        
        if self.prompt_style in [PromptStyle.SYSTEM_USER, PromptStyle.CONVERSATION]:
            system_prompt = self._build_system_prompt(skill)
            messages.append({"role": "system", "content": system_prompt})
            
            user_message = self._build_user_message(skill, context)
            messages.append({"role": "user", "content": user_message})
        
        elif self.prompt_style == PromptStyle.INSTRUCTION_ONLY:
            instruction = self._build_instruction(skill, context)
            messages.append({"role": "user", "content": instruction})
        
        elif self.prompt_style == PromptStyle.XML_TAGGED:
            xml_content = self._build_xml_prompt(skill, context)
            messages.append({"role": "user", "content": xml_content})
        
        elif self.prompt_style == PromptStyle.MARKDOWN:
            md_content = self._build_markdown_prompt(skill, context)
            messages.append({"role": "user", "content": md_content})
        
        return {"messages": messages, "max_tokens": self.max_tokens}
    
    def _build_system_prompt(self, skill: Skill) -> str:
        parts = []
        parts.append(f"你是一个'{skill.name}'技能专家。")
        parts.append(skill.meta.description)
        
        if skill.meta.capabilities:
            parts.append(f"能力列表: {', '.join(skill.meta.capabilities)}")
        
        return "\n".join(parts)
    
    def _build_user_message(self, skill: Skill, context: Dict[str, Any]) -> str:
        parts = []
        
        if "task" in context:
            parts.append(f"任务: {context['task']}")
        
        if "mode" in context:
            parts.append(f"模式: {context['mode']}")
        
        if "parameters" in context:
            parts.append(f"参数: {context['parameters']}")
        
        parts.append("\n请执行此技能并返回结果。")
        
        return "\n".join(parts)
    
    def _build_instruction(self, skill: Skill, context: Dict[str, Any]) -> str:
        return f"""作为'{skill.name}'技能专家，请执行以下任务：

任务: {context.get('task', '')}

参数: {context.get('parameters', {})}

技能描述: {skill.meta.description}

请返回执行结果。"""
    
    def _build_xml_prompt(self, skill: Skill, context: Dict[str, Any]) -> str:
        return f"""<skill>
  <name>{skill.name}</name>
  <description>{skill.meta.description}</description>
  <task>{context.get('task', '')}</task>
  <mode>{context.get('mode', 'default')}</mode>
  <parameters>{context.get('parameters', {})}</parameters>
</skill>

请执行此技能并返回结果。"""
    
    def _build_markdown_prompt(self, skill: Skill, context: Dict[str, Any]) -> str:
        return f"""## 技能执行请求

### 技能信息
- **名称**: {skill.name}
- **描述**: {skill.meta.description}
- **版本**: {skill.meta.version}
- **标签**: {', '.join(skill.meta.tags)}

### 执行参数
- **任务**: {context.get('task', '')}
- **模式**: {context.get('mode', 'default')}
- **参数**: {context.get('parameters', {})}

请执行此技能并返回结果。"""
    
    def adapt_tool_call(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        if self.tool_format == ToolCallFormat.JSON:
            return {
                "tool_name": tool_name,
                "parameters": parameters,
            }
        
        elif self.tool_format == ToolCallFormat.XML:
            param_xml = "".join([f"<{k}>{v}</{k}>" for k, v in parameters.items()])
            return {
                "tool_call": f"<function name=\"{tool_name}\">{param_xml}</function>",
            }
        
        elif self.tool_format == ToolCallFormat.FUNCTION_CALL:
            return {
                "name": tool_name,
                "arguments": parameters,
            }
        
        elif self.tool_format == ToolCallFormat.NATURAL_LANGUAGE:
            param_str = ", ".join([f"{k}={v}" for k, v in parameters.items()])
            return {
                "call": f"调用工具 {tool_name}({param_str})",
            }
        
        elif self.tool_format == ToolCallFormat.MARKDOWN_CODE_BLOCK:
            return {
                "tool_call": f"```json\n{{\"tool\": \"{tool_name}\", \"params\": {parameters}}}\n```",
            }
        
        return {"tool_name": tool_name, "parameters": parameters}
    
    def adapt_output(self, raw_output: str) -> Dict[str, Any]:
        import json
        try:
            return json.loads(raw_output)
        except Exception:
            return {"success": True, "content": raw_output}
    
    def get_adapter_info(self) -> Dict[str, Any]:
        return {
            "target_env": self.target_env.value,
            "prompt_style": self.prompt_style.value,
            "tool_format": self.tool_format.value,
            "context_limit": self.context_limit,
            "max_tokens": self.max_tokens,
        }

class AdapterRegistry:
    _adapters: Dict[TargetEnvironment, SkillAdapter] = {}
    
    @classmethod
    def register_adapter(cls, env: TargetEnvironment, adapter: SkillAdapter):
        cls._adapters[env] = adapter
        logger.info(f"Registered adapter for {env.value}")
    
    @classmethod
    def get_adapter(cls, env: TargetEnvironment) -> Optional[SkillAdapter]:
        if env not in cls._adapters:
            cls._adapters[env] = SkillAdapter(env)
        return cls._adapters[env]
    
    @classmethod
    def list_adapters(cls) -> List[Dict[str, Any]]:
        return [
            {"env": env.value, **adapter.get_adapter_info()}
            for env, adapter in cls._adapters.items()
        ]
    
    @classmethod
    def adapt_skill(cls, skill: Skill, context: Dict[str, Any], target_env: TargetEnvironment) -> Dict[str, Any]:
        adapter = cls.get_adapter(target_env)
        return adapter.adapt_prompt(skill, context)

def adapt_for_environment(skill: Skill, context: Dict[str, Any], environment: str) -> Dict[str, Any]:
    try:
        env = TargetEnvironment(environment.lower())
        return AdapterRegistry.adapt_skill(skill, context, env)
    except ValueError:
        logger.warning(f"Unknown environment: {environment}")
        return {"error": f"Unknown environment: {environment}"}

def get_environment_info(environment: str) -> Dict[str, Any]:
    try:
        env = TargetEnvironment(environment.lower())
        adapter = AdapterRegistry.get_adapter(env)
        return adapter.get_adapter_info()
    except ValueError:
        return {"error": f"Unknown environment: {environment}"}

def list_supported_environments() -> List[str]:
    return [env.value for env in TargetEnvironment]