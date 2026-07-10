# chat_bot —— 纯对话示例（不依赖 brain/fabric）

最简单的独立 LLM 对话。证明「对话」这一项能力离开 AOS 大脑也能跑。

## 3 行启动

```bash
cd examples/chat_bot
pip install -r requirements.txt
python app.py -m "你好，介绍一下你自己"
```

## 配置模型

```bash
export ZHIPU_API_KEY=...     # 默认模型 zhipu/glm-4-flash
# 或
export OPENAI_API_KEY=...    # 用 --model gpt-4o-mini 等
```

`--model` 可覆盖为任何 litellm 支持的模型名。
