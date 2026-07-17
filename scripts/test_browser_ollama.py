"""测试 browser-use + ollama 本地模型。"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


async def main():
    print("测试 browser-use + ollama 本地模型...")
    print("模型: qwen2.5-coder:7b")

    try:
        from browser_use import Agent
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            model="qwen2.5-coder:7b",
            base_url="http://127.0.0.1:11434",
        )
        print("✅ LLM 初始化成功")

        # 简单任务：打开百度，搜索"AI 智能体"，取第一条结果标题
        task = "打开 https://www.baidu.com，在搜索框输入'AI 智能体'，点击搜索按钮，然后告诉我第一条搜索结果的标题"
        print(f"任务: {task}")

        agent = Agent(task=task, llm=llm)
        result = await agent.run()

        print(f"\n✅ 任务完成!")
        print(f"结果: {result}")
        return 0

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("尝试安装依赖: pip install browser-use langchain-ollama")
        return 1
    except Exception as e:
        print(f"❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
