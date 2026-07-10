"""AOS examples/code_review —— 单 skill 核心逻辑独立执行，不依赖 brain/fabric。

读一个代码文件（或目录），用 LLM 做审查，输出改进建议。
等价于 AOS 里某个 code-review skill 的「核心逻辑」脱离大脑独立运行——证明
skill 的能力本身就是自洽的，brain 只是它的调度壳。

3 行启动：
    cd examples/code_review
    pip install -r requirements.txt
    python app.py --file ../src/skills/vimax.py
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

try:
    import litellm
except ImportError:
    sys.exit("缺少 litellm：请先 `pip install -r requirements.txt`")

SYSTEM_PROMPT = (
    "你是一名资深代码审查员。请审查给出的代码，用中文输出：\n"
    "1) 主要问题（正确性 / 安全 / 性能 / 可维护性）\n"
    "2) 关键改进建议（附要点，不必重写全部代码）\n"
    "3) 总体评价（一句话）\n"
    "保持简洁、可执行。"
)


def _collect(files_or_dir: str):
    paths = []
    if os.path.isdir(files_or_dir):
        for ext in ("*.py", "*.js", "*.ts"):
            paths += glob.glob(os.path.join(files_or_dir, "**", ext), recursive=True)
    else:
        paths = [files_or_dir]
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description="AOS 独立代码审查示例（不依赖 brain/fabric）")
    ap.add_argument("--file", "-f", required=True, help="代码文件或目录")
    ap.add_argument("--model", default=os.getenv("AOS_EXAMPLE_MODEL", "zhipu/glm-4-flash"))
    args = ap.parse_args()

    if args.model.startswith("zhipu/") and not os.getenv("ZHIPU_API_KEY"):
        print("⚠️ 使用 zhipu 模型需 export ZHIPU_API_KEY=...")
        return 2

    paths = _collect(args.file)
    if not paths:
        print("未找到代码文件。")
        return 1

    code = ""
    for p in paths[:5]:  # 限制单次审查体量
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                code += f"\n# === {p} ===\n" + f.read()
        except OSError:
            continue

    try:
        resp = litellm.completion(
            model=args.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"请审查以下代码：\n\n{code}"},
            ],
            temperature=0.2,
        )
        print(resp.choices[0].message.content)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"审查失败：{e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
