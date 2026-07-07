"""
DeerFlow Path Detection - 统一的外部依赖路径自动检测
"""

import sys
import os as _os
from pathlib import Path
from typing import Optional

from utils.config import config


def detect_deerflow_path() -> Optional[str]:
    """自动检测 DeerFlow 源码路径"""
    candidates = [
        config.DEERFLOW_HARNESS_PATH,
        config.DEERFLOW_SOURCE_PATH,
        str(Path(config.BASE_DIR) / "external" / "deer-flow" / "backend" / "packages" / "harness"),
        str(Path(config.BASE_DIR) / "external" / "deer-flow" / "backend"),
        str(Path(config.BASE_DIR) / "external" / "deer-flow"),
    ]
    
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            if (Path(candidate) / "deerflow").exists():
                return candidate
            if (Path(candidate) / "packages" / "harness" / "deerflow").exists():
                return str(Path(candidate) / "packages" / "harness")
    
    return None


def setup_deerflow_env() -> Optional[str]:
    """设置 DeerFlow 运行环境"""
    _df_src = detect_deerflow_path()
    
    if _df_src:
        if _df_src in sys.path:
            sys.path.remove(_df_src)
        sys.path.insert(0, _df_src)
        
        config_path = config.DEERFLOW_CONFIG_PATH
        if not config_path or not Path(config_path).exists():
            config_path = str(Path(_df_src) / ".." / ".." / ".." / "config.example.yaml")
        
        _os.environ.setdefault('DEER_FLOW_CONFIG_PATH', config_path)
        
        for _var in ['DEEPSEEK_API_KEY', 'VOLCENGINE_API_KEY', 'ZHIPU_API_KEY', 'SCNET_API_KEY']:
            _os.environ.setdefault(_var, 'dummy-for-aos')
        _os.environ.setdefault('FEISHU_WEBHOOK', 'https://dummy.example.com')
        
        return _df_src
    
    return None


def detect_uitars_path() -> Optional[str]:
    """自动检测 UI-TARS 源码路径"""
    candidates = [
        config.UITARS_CWD,
        config.UITARS_PATH,
        str(Path(config.BASE_DIR) / "external" / "UI-TARS-desktop"),
        str(Path(config.BASE_DIR) / "external" / "uitars"),
    ]
    
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    
    return None


def detect_openclaw_path() -> Optional[str]:
    """自动检测 OpenClaw 源码路径"""
    candidates = [
        config.OPENCLAW_CWD,
        config.OPENCLAW_PATH,
        str(Path(config.BASE_DIR) / "external" / "jiuwenclaw"),
        str(Path(config.BASE_DIR) / "external" / "openclaw"),
    ]
    
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    
    return None