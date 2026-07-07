"""
API密钥安全工具

用于生成和管理安全的API密钥
"""

import bcrypt
import secrets
import getpass


def generate_api_key() -> str:
    """生成安全的API密钥"""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """对API密钥进行哈希处理"""
    if isinstance(api_key, str):
        api_key = api_key.encode('utf-8')
    return bcrypt.hashpw(api_key, bcrypt.gensalt()).decode('utf-8')


def verify_api_key(api_key: str, hashed_key: str) -> bool:
    """验证API密钥"""
    try:
        if isinstance(api_key, str):
            api_key = api_key.encode('utf-8')
        if isinstance(hashed_key, str):
            hashed_key = hashed_key.encode('utf-8')
        return bcrypt.checkpw(api_key, hashed_key)
    except Exception:
        return False


def main():
    """交互式生成API密钥和哈希"""
    print("🔐 AOS API密钥生成工具")
    print("=" * 50)
    
    # 选项1：自动生成
    print("\n1. 自动生成新的API密钥")
    api_key = generate_api_key()
    print(f"生成的API密钥: {api_key}")
    
    # 生成哈希
    hashed = hash_api_key(api_key)
    print(f"哈希值: {hashed}")
    
    # 验证
    print(f"\n验证测试: {verify_api_key(api_key, hashed)}")
    
    # 环境变量配置
    print("\n" + "=" * 50)
    print("环境变量配置:")
    print("=" * 50)
    print(f"# 设置明文API密钥（用于向后兼容）")
    print(f"export AOS_API_KEY=\"{api_key}\"")
    print(f"\n# 设置哈希API密钥（推荐，更安全）")
    print(f"export AOS_API_KEY_HASH=\"{hashed}\"")
    
    # Windows PowerShell配置
    print("\n" + "=" * 50)
    print("Windows PowerShell 配置:")
    print("=" * 50)
    print(f"$env:AOS_API_KEY=\"{api_key}\"")
    print(f"$env:AOS_API_KEY_HASH=\"{hashed}\"")
    
    # 永久设置
    print("\n" + "=" * 50)
    print("永久设置 (PowerShell):")
    print("=" * 50)
    print(f"[System.Environment]::SetEnvironmentVariable('AOS_API_KEY', '{api_key}', 'User')")
    print(f"[System.Environment]::SetEnvironmentVariable('AOS_API_KEY_HASH', '{hashed}', 'User')")
    
    print("\n" + "=" * 50)
    print("✅ 完成！请妥善保管你的API密钥")
    print("=" * 50)


if __name__ == "__main__":
    main()