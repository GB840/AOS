import os
import io
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(title="OfficeWorker", version="1.0.0")

# 安全配置
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "application/json",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}

ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".json", ".jpg", ".jpeg", ".png", ".gif", ".webp"
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILES_PER_REQUEST = 10
SCAN_UPLOADS = True  # 是否启用文件扫描

class ExecuteRequest(BaseModel):
    task: str
    action: str = None
    file_path: str = None
    data: Dict[str, Any] = None

class ExecuteResponse(BaseModel):
    success: bool
    output: str = None
    data: Dict[str, Any] = None
    error: str = None

@app.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest):
    try:
        if request.action == "read_excel":
            result = read_excel(request.file_path)
            return ExecuteResponse(success=True, data=result)
        elif request.action == "write_excel":
            result = write_excel(request.file_path, request.data)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "read_word":
            result = read_word(request.file_path)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "write_word":
            result = write_word(request.file_path, request.data)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "read_pdf":
            result = read_pdf(request.file_path)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "analyze_data":
            result = analyze_data(request.data)
            return ExecuteResponse(success=True, data=result)
        else:
            result = process_task(request.task)
            return ExecuteResponse(success=True, output=result)
    except Exception as e:
        return ExecuteResponse(success=False, error=str(e))

def read_excel(file_path: str) -> Dict[str, Any]:
    import pandas as pd
    df = pd.read_excel(file_path)
    return {
        "columns": df.columns.tolist(),
        "rows": df.to_dict('records'),
        "shape": df.shape
    }

def write_excel(file_path: str, data: Dict[str, Any]) -> str:
    import pandas as pd
    df = pd.DataFrame(data.get("rows", []))
    df.to_excel(file_path, index=False)
    return f"Excel file written to {file_path}"

def read_word(file_path: str) -> str:
    from docx import Document
    doc = Document(file_path)
    return "\n".join([para.text for para in doc.paragraphs])

def write_word(file_path: str, data: Dict[str, Any]) -> str:
    from docx import Document
    doc = Document()
    for paragraph in data.get("paragraphs", []):
        doc.add_paragraph(paragraph)
    doc.save(file_path)
    return f"Word file written to {file_path}"

def read_pdf(file_path: str) -> str:
    import fitz
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def analyze_data(data: Dict[str, Any]) -> Dict[str, Any]:
    import pandas as pd
    if not data.get("rows"):
        return {"error": "No data provided"}
    
    df = pd.DataFrame(data["rows"])
    result = {
        "summary": df.describe().to_dict(),
        "columns": df.columns.tolist(),
        "shape": df.shape,
        "missing_values": df.isnull().sum().to_dict()
    }
    
    if "date_column" in data:
        df[data["date_column"]] = pd.to_datetime(df[data["date_column"]])
        result["time_series"] = df.groupby(data["date_column"]).size().to_dict()
    
    return result

def process_task(task: str) -> str:
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    
    llm = ChatOllama(model="qwen2:7b", base_url="http://localhost:11434")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个办公文档处理专家。请分析用户的办公任务需求。"),
        ("user", "用户任务：{task}\n请分析任务需求并给出处理建议。"),
    ])
    
    chain = prompt | llm
    response = chain.invoke({"task": task})
    return response.content

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """安全文件上传端点"""
    
    # 1. 文件名安全检查
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    
    # 防止路径遍历攻击
    safe_filename = Path(file.filename).name
    if safe_filename != file.filename:
        raise HTTPException(status_code=400, detail="文件名包含非法字符")
    
    # 2. 文件扩展名检查
    file_ext = Path(safe_filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415, 
            detail=f"不支持的文件类型: {file_ext}。允许的类型: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    try:
        # 3. 读取文件内容
        contents = await file.read()
        
        # 4. 文件大小检查
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"文件大小超过限制 ({MAX_FILE_SIZE / (1024*1024):.1f}MB)"
            )
        
        # 5. MIME类型验证（使用文件内容，不依赖扩展名）
        try:
            import magic
            mime = magic.Magic(mime=True)
            detected_mime = mime.from_buffer(contents)
            
            if detected_mime not in ALLOWED_MIME_TYPES:
                raise HTTPException(
                    status_code=415,
                    detail=f"检测到不支持的文件类型: {detected_mime}"
                )
        except ImportError:
            logger.warning("python-magic未安装，跳过MIME类型验证")
        except Exception as e:
            logger.warning(f"MIME类型验证失败: {e}")
        
        # 6. 文件内容安全扫描（可选）
        if SCAN_UPLOADS:
            scan_result = await _scan_file_content(contents, safe_filename)
            if not scan_result["safe"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"文件安全扫描失败: {scan_result['reason']}"
                )
        
        # 7. 生成安全的文件路径
        file_hash = hashlib.md5(contents).hexdigest()[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file_hash}_{safe_filename}"
        
        file_path = Path("uploads") / safe_filename
        
        # 8. 确保上传目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 9. 安全写入文件
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # 10. 记录上传日志
        logger.info(f"文件上传成功: {safe_filename} ({len(contents)} bytes, MIME: {detected_mime if 'detected_mime' in locals() else 'unknown'})")
        
        return {
            "success": True,
            "file_path": str(file_path),
            "original_filename": file.filename,
            "size": len(contents),
            "mime_type": detected_mime if 'detected_mime' in locals() else "unknown",
            "upload_time": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        return {"success": False, "error": f"文件上传失败: {str(e)}"}


@app.post("/upload/multiple")
async def upload_multiple_files(files: List[UploadFile] = File(...)):
    """批量安全文件上传"""
    
    # 检查文件数量
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"文件数量超过限制 (最多{MAX_FILES_PER_REQUEST}个)"
        )
    
    results = []
    successful_uploads = 0
    
    for file in files:
        try:
            result = await upload_file(file)
            if result.get("success"):
                successful_uploads += 1
            results.append(result)
        except Exception as e:
            results.append({
                "success": False,
                "filename": file.filename if file.filename else "unknown",
                "error": str(e)
            })
    
    return {
        "success": True,
        "total_files": len(files),
        "successful_uploads": successful_uploads,
        "failed_uploads": len(files) - successful_uploads,
        "results": results
    }


async def _scan_file_content(contents: bytes, filename: str) -> dict:
    """
    文件内容安全扫描
    
    简单实现：检查文件内容中的危险模式
    可以扩展为集成真正的病毒扫描软件
    """
    try:
        content_str = contents.decode('utf-8', errors='ignore')
        
        # 检查危险模式
        dangerous_patterns = [
            '<script',  # JavaScript
            '<?php',    # PHP
            '<%',       # ASP
            '#!/bin/',  # Shell脚本
            '#!/usr/bin/',
        ]
        
        for pattern in dangerous_patterns:
            if pattern.lower() in content_str.lower():
                return {
                    "safe": False,
                    "reason": f"文件包含可疑内容: {pattern}"
                }
        
        # 检查是否为可执行文件
        if contents[:2] == b'MZ':  # Windows可执行文件
            return {
                "safe": False,
                "reason": "检测到可执行文件"
            }
        
        return {"safe": True}
        
    except Exception as e:
        logger.warning(f"文件扫描失败: {e}")
        # 扫描失败不阻止上传，但记录警告
        return {"safe": True, "warning": f"扫描失败: {str(e)}"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "OfficeWorker"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)