import subprocess
p = subprocess.Popen(
    [r"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe",
     "examples/lifeform_self_evolve_demo.py"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=r"D:/AOS",
    encoding="utf-8", errors="replace")
try:
    out, _ = p.communicate(timeout=45)
except subprocess.TimeoutExpired:
    p.kill(); out, _ = p.communicate()
    out += "\n\n[WRAPPER] 45s 超时, 进程被强制杀死 (疑似卡在 LLM/网络调用)\n"
print(out[-4500:])
