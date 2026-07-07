import sys
import os
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="CodeWorker", version="1.0.0")

class ExecuteRequest(BaseModel):
    task: str
    files: Dict[str, str] = None
    command: str = None

class ExecuteResponse(BaseModel):
    success: bool
    output: str = None
    error: str = None

@app.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest):
    try:
        if request.command:
            result = await run_command(request.command)
            return ExecuteResponse(success=True, output=result)
        
        if request.task:
            result = await analyze_and_code(request.task)
            return ExecuteResponse(success=True, output=result)
        
        return ExecuteResponse(success=False, error="No task or command provided")
    except Exception as e:
        return ExecuteResponse(success=False, error=str(e))

async def run_command(command: str) -> str:
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.getcwd()
    )
    stdout, stderr = await process.communicate()
    output = stdout.decode('utf-8', errors='replace')
    if stderr:
        output += "\nSTDERR: " + stderr.decode('utf-8', errors='replace')
    return output

async def analyze_and_code(task: str) -> str:
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    
    llm = ChatOllama(model="qwen2:7b", base_url="http://localhost:11434")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个专业的Python代码助手。请分析用户需求并提供代码解决方案。"),
        ("user", "用户需求：{task}\n请提供完整的Python代码解决方案。"),
    ])
    
    chain = prompt | llm
    response = await chain.ainvoke({"task": task})
    
    return response.content

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "CodeWorker"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)