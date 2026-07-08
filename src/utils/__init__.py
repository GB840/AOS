from .config import config

__all__ = ["config"]

# 兼容 Hermes vendored 代码的 `from utils import X` (解决 utils 包名撞车):
# PYTHONPATH 含 D:/AOS/src 时, `import utils` 会先命中本包, 遮挡
# external/hermes-agent/utils.py, 导致 Hermes 调 `from utils import safe_json_loads`
# 抛 ImportError 并回落云端。这里把 Hermes utils 的公开符号重导出到本包命名空间,
# 既满足 Hermes 的 import, 又不破坏 AOS 自身的 utils.config。
try:
    import importlib.util
    import os
    _hermes_utils_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "external", "hermes-agent", "utils.py",
    )
    if os.path.exists(_hermes_utils_path):
        _spec = importlib.util.spec_from_file_location(
            "_aos_hermes_utils_bridge", _hermes_utils_path
        )
        _hu = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_hu)
        for _n in dir(_hu):
            if not _n.startswith("_"):
                globals().setdefault(_n, getattr(_hu, _n))
except Exception:
    # 加载失败静默跳过: Hermes 调用时仍回落云端, 不影响 AOS 核心启动
    pass
