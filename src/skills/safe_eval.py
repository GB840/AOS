"""安全的表达式求值器 (替代 eval)。

用于校验规则 / 条件表达式 (如 result["x"] == "y", len(context["k"]) > 3)。
仅允许受限的 AST 子集, 杜绝 eval 带来的代码注入 (无属性访问 / 无导入 / 无任意调用)。
"""
import ast
from typing import Any, Dict


def safe_eval_expr(expr: str, variables: Dict[str, Any]) -> bool:
    """在 variables 作用域内安全求值布尔表达式。

    返回 bool; 任何不合法 / 越权 / 异常都返回 False (fail-closed)。
    允许的语法: 在 variables 中的变量名、对变量的字符串下标访问、
    比较 (== != < > <= >= is is not)、布尔 and/or、not、len()、常量。
    """
    if not isinstance(expr, str) or not expr.strip():
        return False
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Expression):
            continue
        # 运算符 / 表达式上下文节点 (Eq/And/Load 等) 由父节点约束, 此处直接跳过。
        elif isinstance(node, (ast.cmpop, ast.boolop, ast.unaryop,
                               ast.operator, ast.expr_context)):
            continue
        elif isinstance(node, ast.BoolOp):
            if not isinstance(node.op, (ast.And, ast.Or)):
                return False
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.Not, ast.USub)):
                return False
        elif isinstance(node, ast.Compare):
            for op in node.ops:
                if not isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.Gt,
                                       ast.LtE, ast.GtE, ast.Is, ast.IsNot)):
                    return False
        elif isinstance(node, ast.Subscript):
            # 仅允许对 variables 中的变量做字符串键下标访问
            if not isinstance(node.value, ast.Name) or node.value.id not in variables:
                return False
            if not (isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)):
                return False
        elif isinstance(node, ast.Name):
            # 允许 variables 中的变量, 以及唯一的许可内建调用名 len (其函数名节点)。
            if node.id not in variables and node.id != "len":
                return False
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (str, int, float, bool, type(None))):
                return False
        elif isinstance(node, ast.Call):
            # 仅允许 len(...)
            if not (isinstance(node.func, ast.Name) and node.func.id == "len"):
                return False
            if len(node.args) != 1:
                return False
        else:
            # Attribute / Import / Lambda / ListComp / 任意其它节点一律禁止
            return False

    try:
        result = eval(compile(tree, "<rule>", "eval"), {}, dict(variables))
        return bool(result)
    except Exception:
        return False
