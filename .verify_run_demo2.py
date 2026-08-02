import subprocess
p = subprocess.Popen(
    [r"C:/Users/Administrator/.workbuddy/binaries/python/envs/aos/Scripts/python.exe",
     "examples/lifeform_self_evolve_demo.py"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=r"D:/AOS",
    encoding="utf-8", errors="replace")
try:
    out, _ = p.communicate(timeout=120)
except subprocess.TimeoutExpired:
    p.kill(); out, _ = p.communicate()
    out += "\n\n[WRAPPER] 120s 超时, 进程被杀 (卡在 LLM/网络)\n"
print(out[-6000:])
