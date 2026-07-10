"""直连测试三个 mistralrs 端点的真实生成能力，并验证 model 字段是否必须匹配。"""
from openai import OpenAI

ENDPOINTS = [
    # (port, served_model_id, label, ascii_prompt)
    (1234, r"C:\Users\Administrator\MiniCPM5-1B-GGUF", "MiniCPM5(GENERAL)",
     "Reply with one short sentence: what are you?"),
    (1235, r"D:\models\Qwen2.5-Coder-3B-Instruct", "Qwen2.5-Coder(CODING)",
     "Write a one-line python function to sum a list."),
    (1236, r"D:\models\DeepSeek-R1-1.5B", "DeepSeek-R1(REASONING)",
     "What is 12 * 13? Show the reasoning in one sentence."),
]

DUMMY_NAME = "totally-wrong-model-name"  # 用于验证 mistralrs 是否校验 model 字段

def chat(port, model, prompt, timeout=120):
    client = OpenAI(base_url=f"http://localhost:{port}/v1", api_key="mistralrs")
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.3,
        )
        return True, r.choices[0].message.content.strip()
    except Exception as e:
        return False, f"ERROR: {type(e).__name__}: {str(e)[:200]}"

if __name__ == "__main__":
    print("############ A. 用真实 served model id 直连生成 ############")
    for port, mid, label, prompt in ENDPOINTS:
        ok, out = chat(port, mid, prompt)
        print(f"\n--- {label} @ :{port} (model={mid}) ---")
        print(f"  OK={ok}\n  >> {out}")

    print("\n\n############ B. 故意用错误 model 名，验证是否校验 ############")
    for port, mid, label, prompt in ENDPOINTS:
        ok, out = chat(port, DUMMY_NAME, prompt)
        print(f"\n--- {label} @ :{port} (model={DUMMY_NAME}) ---")
        print(f"  OK={ok}\n  >> {out[:160]}")
