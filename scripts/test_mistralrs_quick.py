"""轻量验证：mistralrs 是否校验 model 字段 + 每端口极短生成证明可用。"""
from openai import OpenAI

CASES = [
    # (port, served_id, config_short_name, label)
    (1234, r"C:\Users\Administrator\MiniCPM5-1B-GGUF", "minicpm5-1b", "MiniCPM5"),
    (1235, r"D:\models\Qwen2.5-Coder-3B-Instruct", "qwen2.5-coder-3b", "Qwen-Coder"),
    (1236, r"D:\models\DeepSeek-R1-1.5B", "deepseek-r1-1.5b", "DeepSeek"),
]

def chat(port, model, prompt="Say hi in 3 words.", max_tokens=16, timeout=90):
    c = OpenAI(base_url=f"http://localhost:{port}/v1", api_key="mistralrs")
    try:
        r = c.chat.completions.create(model=model, messages=[{"role":"user","content":prompt}],
                                      max_tokens=max_tokens, temperature=0.2)
        return True, r.choices[0].message.content.strip()
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}"

if __name__ == "__main__":
    print("### 用路由配置里的【短名】(minicpm5-1b / qwen2.5-coder-3b / deepseek-r1-1.5b) 直连 ###")
    for port, served, short, label in CASES:
        ok, out = chat(port, short)
        print(f"[{label} :{port}] model={short!r} -> OK={ok} | {out!r}")
    print("\n### 对照：用真实 served id ###")
    for port, served, short, label in CASES:
        ok, out = chat(port, served)
        print(f"[{label} :{port}] model={served!r} -> OK={ok} | {out!r}")
