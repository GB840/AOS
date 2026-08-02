import subprocess, sys, os

AOSPY = r"C:/Users/Administrator/.workbuddy/binaries/python/envs/aos/Scripts/python.exe"
env = dict(os.environ)
env["AOS_REFLECT_OFF"] = "1"  # 跳过 LLM，验证蒸馏器降级（②）路径
p = subprocess.Popen(
    [AOSPY, "examples/lifeform_self_evolve_demo.py"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=r"D:/AOS",
    encoding="utf-8", errors="replace", env=env,
)
try:
    out, _ = p.communicate(timeout=120)
except subprocess.TimeoutExpired:
    p.kill(); out, _ = p.communicate()
    out += "\n\n[WRAPPER] 120s 超时\n"
print(out[-4500:])
try:
    os.remove(__file__)
except Exception:
    pass
