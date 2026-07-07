"""
AOS 技能系统 (Skills System)
============================
基于 agentskills.io 标准的自进化技能引擎。

技能生命周期: 发现(Find) → 创建(Create) → 注册(Register) → 执行(Execute) → 进化(Evolve)
元技能: Skill Creator / Find Skills — 可自我创造新技能
流程技能: Superpowers / J Stack — 工作流编排
设计技能: Frontend Design / UI-UX Pro Max — 界面生成
搜索技能: DuckDuckGo Search — 免费网络搜索

懒加载优化: Agency角色按需加载，避免启动延迟
"""

import importlib
import logging
from pathlib import Path
from typing import Callable, Dict, Any

from .base import Skill, SkillRegistry, SkillMeta
from .skill_creator import SkillCreator
from .find_skills import FindSkills
from .superpowers import SuperpowersSkill
from .j_stack import JStackSkill
from .frontend_design import FrontendDesignSkill
from .ui_ux_promax import UIUXProMaxSkill
from .duckduckgo_search import DuckDuckGoSearchSkill
from .template import SkillTemplate, StageSpec, ToolSpec, TestCase
from .factory import SkillFactory, TemplateSkill
from .engineering import EngineeringSkill, CodeQualityChecker
from .adapter import SkillAdapter, AdapterRegistry, TargetEnvironment, adapt_for_environment
from .versioning import SkillVersionManager, SnapshotManager, get_version_manager, get_snapshot_manager
from .marketplace import SkillMarketplace, SkillImporter, get_marketplace, get_importer
from .composition import SkillCompositionEngine, CombinationStrategy, SkillPipeline
from .learning import SkillLearningSystem, FeedbackRecord, get_learning_system
from .sandbox import SkillSandbox, SandboxConfig, SandboxResult, get_sandbox
from .monitoring import SkillMonitor, SkillSpan, SkillMetric, get_monitor
from .loop_engineering import LoopEngineeringSkill
from .vimax import ViMaxSkill
from .ruflo import RuFloSkill
from .pixelle_video import PixelleVideoSkill
from .codebase_memory import CodebaseMemorySkill
from .searxng import SearXNGSkill
from .lightrag import LightRAGSkill
from .jina_reader import JinaReaderSkill
from .ollama import OllamaSkill
from .viitor_voice import ViiTorVoiceSkill
from .uitars import UITarsSkill
from .zvec import ZvecSkill
from .llama_cpp import LlamaCppSkill
from .comfyui import ComfyUISkill
from .codebase_memory_mcp import CodebaseMemoryMCPSkill
from .agency_agents import AgencyAgentsSkill
from .omni_route import OmniRouteSkill
from .open_montage import OpenMontageSkill
from .video_use import VideoUseSkill
from .cognee import CogneeSkill
from .herdr import HerdrSkill
from .design_md import DesignMdSkill
from .no_mistakes import NoMistakesSkill
from .lingbot_map import LingbotMapSkill

logger = logging.getLogger(__name__)

# ---- Agency Roles 懒加载系统 ----

_AGENCY_ROLES_PATH = Path("src/skills/agency_roles")
_AGENCY_SKILLS_LOADERS: Dict[str, Callable[[], Any]] = {}
_AGENCY_SKILLS_CACHE: Dict[str, Any] = {}


def _init_agency_lazy_loading():
    """初始化Agency角色懒加载映射"""
    if not _AGENCY_ROLES_PATH.exists():
        logger.warning(f"Agency角色目录不存在: {_AGENCY_ROLES_PATH}")
        return
    
    role_files = list(_AGENCY_ROLES_PATH.glob("*.py"))
    logger.info(f"发现 {len(role_files)} 个Agency角色文件，准备懒加载")
    
    for role_file in role_files:
        skill_name = role_file.stem
        
        # 跳过特殊文件
        if skill_name.startswith("_"):
            continue
        
        def create_loader(file_path=role_file, name=skill_name):
            def loader():
                # 检查缓存
                if name in _AGENCY_SKILLS_CACHE:
                    return _AGENCY_SKILLS_CACHE[name]
                
                # 懒加载
                logger.info(f"懒加载Agency角色: {name}")
                try:
                    module = importlib.import_module(f"src.skills.agency_roles.{name}")
                    skill = getattr(module, 'AgentRole', None)
                    if skill is None:
                        raise AttributeError(f"模块 {name} 中没有找到 AgentRole 类")
                    
                    instance = skill()
                    _AGENCY_SKILLS_CACHE[name] = instance
                    return instance
                except Exception as e:
                    logger.error(f"加载Agency角色 {name} 失败: {e}")
                    raise
            return loader
        
        _AGENCY_SKILLS_LOADERS[skill_name] = create_loader()


def get_agency_skill_lazy(skill_name: str) -> Any:
    """获取Agency角色实例（懒加载）"""
    if skill_name not in _AGENCY_SKILLS_LOADERS:
        available = list(_AGENCY_SKILLS_LOADERS.keys())
        raise ValueError(
            f"Agency角色 '{skill_name}' 不存在。可用角色: {available[:10]}..." 
            if len(available) > 10 else f"Agency角色 '{skill_name}' 不存在。可用角色: {available}"
        )
    
    return _AGENCY_SKILLS_LOADERS[skill_name]()


def list_agency_skills() -> list:
    """列出所有可用的Agency角色"""
    return list(_AGENCY_SKILLS_LOADERS.keys())


def preload_agency_skills(skill_names: list = None):
    """预加载指定的Agency角色"""
    if skill_names is None:
        skill_names = list(_AGENCY_SKILLS_LOADERS.keys())
    
    logger.info(f"预加载 {len(skill_names)} 个Agency角色...")
    loaded_count = 0
    failed_skills = []
    
    for skill_name in skill_names:
        try:
            get_agency_skill_lazy(skill_name)
            loaded_count += 1
        except Exception as e:
            failed_skills.append((skill_name, str(e)))
    
    logger.info(f"预加载完成: {loaded_count} 成功, {len(failed_skills)} 失败")
    if failed_skills:
        for skill_name, error in failed_skills:
            logger.warning(f"预加载失败 {skill_name}: {error}")


# 原有的立即加载方式（兼容性保留）
def register_agency_roles():
    """立即注册所有Agency角色（已弃用，建议使用懒加载）"""
    logger.warning("使用立即加载方式注册Agency角色，建议改用懒加载以提高启动速度")
    preload_agency_skills()


# 初始化懒加载系统（不立即加载）
_init_agency_lazy_loading()
