"""单创OS API schema 守门测试（2026-08-08 实跑发现真 bug 后新增）。

背景（真实故障，非假设）：
    `src/api/danchuang_api.py` 头部有 `from __future__ import annotations`，
    而 7+3 个 Pydantic 请求模型原先定义在 `register_routes()` 函数体内。
    FastAPI 解析端点签名用 `get_type_hints()`，只查【模块全局命名空间】，
    看不见函数内的局部类，于是：

    1. GET /openapi.json → 500
       PydanticUserError: `TypeAdapter[Annotated[ForwardRef('TenantRegisterRequest'), ...]]`
       is not fully defined  → 连带 /docs 文档页整页空白。
    2. 更严重：POST /api/danchuang/tenant/register 实测返回
       422 {"detail":[{"loc":["query","req"],"msg":"Field required"}]}
       —— FastAPI 解析不出模型，把 body 参数降级成了 query 参数，
       整个单创OS 的写接口全废（注册租户/设目标/建工作流/BYOK 存 Key）。

本测试锁死三件事：
    - OpenAPI schema 能完整生成（防 500 回归）
    - 关键 POST 端点的入参落在 requestBody 而非 query（防降级回归）
    - 全库 AST 守门：有 future annotations 的文件里禁止在函数内定义 BaseModel 子类
"""
from __future__ import annotations

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"


# ──────────────────────────────────────────────────────────────
# 1. OpenAPI schema 必须能生成（防 /openapi.json 500 + /docs 空白）
# ──────────────────────────────────────────────────────────────

def _build_app():
    """只挂 danchuang 路由，避免拉起整个 main:app 的重依赖。"""
    from fastapi import FastAPI

    from api import danchuang_api

    app = FastAPI()
    danchuang_api.register_routes(app)
    return app


def test_openapi_schema_generates_without_error():
    """回归：ForwardRef 未解析会让 openapi() 抛 PydanticUserError。"""
    app = _build_app()
    spec = app.openapi()  # 修复前此处直接抛 PydanticUserError
    assert isinstance(spec, dict)
    assert spec.get("paths"), "OpenAPI 没有任何路径，schema 生成不完整"


def test_request_models_are_resolvable_at_module_level():
    """请求模型必须能从模块全局命名空间拿到（FastAPI 解析注解的前提）。"""
    from api import danchuang_api

    expected = [
        "TenantRegisterRequest",
        "SetGoalRequest",
        "ReviewRequest",
        "AdjustRequest",
        "CreateWorkflowRequest",
        "CompleteStepRequest",
        "CrewRunRequest",
        "ByokSaveRequest",
        "ByokTestRequest",
        "ByokChatRequest",
    ]
    missing = [n for n in expected if not hasattr(danchuang_api, n)]
    assert not missing, f"以下请求模型不在模块级，FastAPI 将解析不到: {missing}"


# ──────────────────────────────────────────────────────────────
# 2. POST 入参必须是 requestBody，不能被降级成 query
# ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "path",
    [
        "/api/danchuang/tenant/register",
        "/api/danchuang/goal/set",
        "/api/danchuang/workflows",
        "/api/danchuang/byok/save",
    ],
)
def test_key_post_endpoints_have_request_body(path):
    """回归：模型解析不到时 FastAPI 会把 body 降级成 query 参数。"""
    spec = _build_app().openapi()
    op = spec["paths"].get(path, {}).get("post")
    if op is None:
        pytest.skip(f"{path} 未注册（可能依赖可选组件），跳过")

    assert "requestBody" in op, f"{path} 缺少 requestBody —— 入参被降级成 query 了"


def test_no_post_endpoint_leaks_model_param_into_query():
    """全量守门：任何 POST 端点都不该出现 req/request/body 这种模型名 query 参数。

    这是 ForwardRef 解析失败的典型指纹 —— FastAPI 认不出 Pydantic 模型时，
    会把整个模型参数当成普通标量塞进 query。
    """
    spec = _build_app().openapi()
    leaked: list[str] = []
    suspicious = {"req", "request", "body", "payload"}

    for path, ops in spec["paths"].items():
        op = ops.get("post")
        if not op:
            continue
        for param in op.get("parameters", []):
            if param.get("in") == "query" and param.get("name") in suspicious:
                leaked.append(f"{path} -> query.{param['name']}")

    assert not leaked, "以下 POST 端点的模型参数被降级成了 query：\n  " + "\n  ".join(leaked)


# ──────────────────────────────────────────────────────────────
# 3. 全库 AST 守门：future annotations + 函数内 BaseModel = 禁止
# ──────────────────────────────────────────────────────────────

def _has_future_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(n, ast.ImportFrom)
        and n.module == "__future__"
        and any(a.name == "annotations" for a in n.names)
        for n in tree.body
    )


def _is_basemodel_subclass(node: ast.ClassDef) -> bool:
    return any(
        (isinstance(b, ast.Name) and b.id == "BaseModel")
        or (isinstance(b, ast.Attribute) and b.attr == "BaseModel")
        for b in node.bases
    )


def test_no_function_scoped_pydantic_models_with_future_annotations():
    """全库守门：任何人再把 Pydantic 请求模型塞进函数体，这里立刻红灯。"""
    offenders: list[str] = []

    for path in SRC.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "BaseModel" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        if not _has_future_annotations(tree):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sub in node.body:
                if isinstance(sub, ast.ClassDef) and _is_basemodel_subclass(sub):
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    offenders.append(f"{rel}:{sub.lineno} {node.name}() -> class {sub.name}")

    assert not offenders, (
        "以下文件同时有 `from __future__ import annotations` 和函数内 Pydantic 模型，"
        "FastAPI 将无法解析注解（openapi 500 / body 降级为 query）：\n  "
        + "\n  ".join(offenders)
    )
