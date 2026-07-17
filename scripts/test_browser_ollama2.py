"""测试 browser-use + ollama OpenAI 兼容模式。"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


async def main():
    print("测试 browser-use + ollama（OpenAI 兼容模式）...")

    try:
        from browser_use import Agent
        from openai import OpenAI

        # 用 OpenAI 客户端连本地 ollama
        client = OpenAI(
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        )

        # 测试一下 chat 能不能通
        resp = client.chat.completions.create(
            model="qwen2.5-coder:7b",
            messages=[{"role": "user", "content": "说一句话"}],
            max_tokens=50,
        )
        print(f"✅ OpenAI 兼容接口通了: {resp.choices[0].message.content[:30]}...")

        # 简单任务
        task = "打开 https://www.baidu.com，搜索'AI智能体'，然后告诉我第一条结果的标题"
        print(f"任务: {task}")

        agent = Agent(task=task, llm=client, model="qwen2.5-coder:7b")
        result = await agent.run()

        print(f"\n✅ 任务完成!")
        print(f"结果: {str(result)[:200]}")
        return 0

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return 1
    except Exception as e:
        print(f"❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
