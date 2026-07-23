import sys
sys.path.insert(0, 'src')

print('检查关键库...')

try:
    import langgraph
    print(f'✅ langgraph 导入成功 (module: {langgraph.__name__})')
except Exception as e:
    print(f'❌ langgraph 导入失败: {e}')

try:
    import langchain_core
    print(f'✅ langchain_core 导入成功 (version: {langchain_core.__version__})')
except Exception as e:
    print(f'❌ langchain_core 导入失败: {e}')

try:
    import crewai
    print(f'✅ crewai 导入成功 (version: {crewai.__version__})')
except Exception as e:
    print(f'❌ crewai 导入失败: {e}')

try:
    from langgraph.graph import StateGraph, START, END
    print('✅ langgraph StateGraph 可用')
except Exception as e:
    print(f'❌ langgraph StateGraph 失败: {e}')

try:
    from crewai import Agent, Task, Crew
    print('✅ crewai Agent/Task/Crew 可用')
except Exception as e:
    print(f'❌ crewai 核心类失败: {e}')
