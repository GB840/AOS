import os
import secrets

import requests

# 严禁硬编码口令: 优先读环境变量 (与 config.py 的 AOS_DEERFLOW_ADMIN_* 对齐,
# 兼容旧 DEERFLOW_ADMIN_* 名), 否则生成随机强口令 (初始化一次性使用, 仅本次输出)。
admin_user = (os.environ.get("AOS_DEERFLOW_ADMIN_USER")
              or os.environ.get("DEERFLOW_ADMIN_USER", "admin"))
admin_pass = (os.environ.get("AOS_DEERFLOW_ADMIN_PASSWORD")
              or os.environ.get("DEERFLOW_ADMIN_PASSWORD")
              or secrets.token_urlsafe(24))

response = requests.post(
    "http://localhost:8080/api/v1/auth/initialize",
    json={"username": admin_user, "password": admin_pass, "email": "admin@aos.com"}
)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
if response.ok:
    print(f"[init] DeerFlow admin '{admin_user}' initialized. 口令: {admin_pass} "
          f"(请妥善保管, 仅本次初始化输出)")
