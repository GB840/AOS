import asyncio
import sys
import pytest
sys.path.insert(0, str(__file__).rsplit('/', 1)[0] if '/' in str(__file__) else str(__file__).rsplit('\\', 1)[0])

pytest.importorskip("deerflow.graph")
from deerflow.graph import PlannerAgent

async def test_planner():
    print("Initializing Planner Agent...")
    planner = PlannerAgent(ollama_base_url="http://localhost:11434", model="qwen2.5:7b")
    
    test_tasks = [
        "帮我写一个Python脚本，计算1到100的和",
        "分析这个任务：读取Excel文件并生成报表",
        "打开记事本应用",
    ]
    
    for task in test_tasks:
        print(f"\n{'='*60}")
        print(f"测试任务: {task}")
        print(f"{'='*60}")
        
        try:
            result = await planner.run(task)
            print(f"\n任务ID: {result['task_id']}")
            print(f"任务状态: {result['task_status']}")
            print(f"\n步骤规划:")
            for i, step in enumerate(result['plan']):
                print(f"  {i+1}. [{step['worker_type']}] {step['description']} - {step['status']}")
            
            if 'final_summary' in result['results']:
                print(f"\n最终总结: {result['results']['final_summary']}")
            else:
                print(f"\n执行结果: {result['results']}")
                
        except Exception as e:
            print(f"\n错误: {e}")

if __name__ == "__main__":
    asyncio.run(test_planner())