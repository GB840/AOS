"""版本发布辅助脚本——打tag + 更新CHANGELOG + 生成发布摘要。

用法:
  python scripts/release.py 0.2.0
  python scripts/release.py 0.2.0 --push
"""
import os
import re
import subprocess
import sys
from datetime import datetime


def get_version_from_changelog() -> str:
    """从CHANGELOG.md读取最新版本号。"""
    changelog = os.path.join(os.path.dirname(__file__), "..", "CHANGELOG.md")
    with open(changelog, "r", encoding="utf-8") as f:
        content = f.read()
    # 找 [Unreleased] 之后的第一个版本号
    match = re.search(r"## \[(\d+\.\d+\.\d+)\]", content)
    return match.group(1) if match else "unknown"


def run(cmd: list, check=True):
    """执行git命令。"""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"命令失败: {' '.join(cmd)}")
        print(f"错误: {result.stderr}")
        sys.exit(1)
    return result


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/release.py <version> [--push]")
        print("示例: python scripts/release.py 0.2.0")
        sys.exit(1)

    version = sys.argv[1]
    do_push = "--push" in sys.argv

    # 验证版本号格式
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        print(f"无效版本号: {version}，格式应为 X.Y.Z")
        sys.exit(1)

    print(f"准备发布版本 {version}...")

    # 1. 检查工作区是否干净
    status = run(["git", "status", "--porcelain"], check=False)
    if status.stdout.strip():
        print("警告: 工作区有未提交的更改")
        resp = input("是否继续? (y/N): ")
        if resp.lower() != "y":
            sys.exit(0)

    # 2. 更新CHANGELOG.md
    changelog = os.path.join(os.path.dirname(__file__), "..", "CHANGELOG.md")
    today = datetime.now().strftime("%Y-%m-%d")
    with open(changelog, "r", encoding="utf-8") as f:
        content = f.read()
    # 把 [Unreleased] 改为具体版本号
    content = content.replace(
        "[Unreleased]",
        f"[Unreleased]\n\n## [{version}] - {today}",
        1
    )
    with open(changelog, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"已更新 CHANGELOG.md → [{version}] - {today}")

    # 3. git commit
    run(["git", "add", "CHANGELOG.md"])
    run(["git", "commit", "-m", f"chore: release v{version}"])
    print(f"已创建 commit: chore: release v{version}")

    # 4. git tag
    run(["git", "tag", f"v{version}"])
    print(f"已创建 tag: v{version}")

    # 5. 输出摘要
    print(f"\n发布准备完成:")
    print(f"  版本: v{version}")
    print(f"  日期: {today}")
    print(f"  Tag:  v{version}")
    if do_push:
        run(["git", "push"])
        run(["git", "push", "--tags"])
        print("  已推送到远端")
    else:
        print(f"\n执行以下命令推送到远端:")
        print(f"  git push")
        print(f"  git push --tags")


if __name__ == "__main__":
    main()
