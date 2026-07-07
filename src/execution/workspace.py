"""
Workspace Manager - 工作空间管理器

管理用户工作空间，支持：
- 工作空间创建与销毁
- 文件管理
- 目录结构管理
- 文件内容读取/写入
- 工作空间隔离

标准：文件系统标准
"""

import os
import sys
import json
import logging
import uuid
import shutil
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from utils.config import config


class WorkspaceManager:
    """工作空间管理器 - 管理用户工作空间"""
    
    def __init__(self):
        self._workspaces = {}
        self._base_dir = Path(config.DATA_DIR) / "workspaces"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"WorkspaceManager initialized, base dir: {self._base_dir}")
    
    def create_workspace(self, 
                        name: str = None,
                        description: str = None) -> Dict[str, Any]:
        """创建工作空间"""
        workspace_id = str(uuid.uuid4())[:8]
        workspace_name = name or f"workspace_{workspace_id}"
        
        workspace_dir = self._base_dir / workspace_id
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        workspace = {
            "id": workspace_id,
            "name": workspace_name,
            "description": description or "",
            "path": str(workspace_dir),
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "modified_at": datetime.now().isoformat(),
            "files": [],
        }
        
        self._workspaces[workspace_id] = workspace
        logger.info(f"工作空间创建成功: {workspace_id} - {workspace_name}")
        
        return {"success": True, "workspace": workspace}
    
    def get_workspace(self, workspace_id: str) -> Dict[str, Any]:
        """获取工作空间"""
        workspace = self._workspaces.get(workspace_id)
        
        if not workspace:
            return {"success": False, "error": f"工作空间不存在: {workspace_id}"}
        
        workspace["files"] = self._list_files(workspace["path"])
        
        return {"success": True, "workspace": workspace}
    
    def list_workspaces(self) -> Dict[str, Any]:
        """列出所有工作空间"""
        workspaces_info = []
        
        for workspace_id, workspace in self._workspaces.items():
            workspaces_info.append({
                "id": workspace_id,
                "name": workspace["name"],
                "description": workspace["description"],
                "status": workspace["status"],
                "created_at": workspace["created_at"],
                "modified_at": workspace["modified_at"],
            })
        
        return {
            "success": True,
            "workspaces": workspaces_info,
            "count": len(workspaces_info),
        }
    
    def delete_workspace(self, workspace_id: str) -> Dict[str, Any]:
        """删除工作空间"""
        workspace = self._workspaces.get(workspace_id)
        
        if not workspace:
            return {"success": False, "error": f"工作空间不存在: {workspace_id}"}
        
        try:
            workspace_dir = Path(workspace["path"])
            
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir)
            
            del self._workspaces[workspace_id]
            
            logger.info(f"工作空间已删除: {workspace_id}")
            return {"success": True, "message": f"工作空间 {workspace_id} 已删除"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def write_file(self, 
                   workspace_id: str,
                   file_path: str,
                   content: str) -> Dict[str, Any]:
        """写入文件"""
        workspace = self._workspaces.get(workspace_id)
        
        if not workspace:
            return {"success": False, "error": f"工作空间不存在: {workspace_id}"}
        
        try:
            full_path = Path(workspace["path"]) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            workspace["modified_at"] = datetime.now().isoformat()
            
            logger.info(f"文件写入成功: {workspace_id}/{file_path}")
            return {"success": True, "message": f"文件 {file_path} 已写入"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def read_file(self, 
                  workspace_id: str,
                  file_path: str) -> Dict[str, Any]:
        """读取文件"""
        workspace = self._workspaces.get(workspace_id)
        
        if not workspace:
            return {"success": False, "error": f"工作空间不存在: {workspace_id}"}
        
        try:
            full_path = Path(workspace["path"]) / file_path
            
            if not full_path.exists():
                return {"success": False, "error": f"文件不存在: {file_path}"}
            
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            return {"success": True, "content": content, "file_path": file_path}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def list_files(self, workspace_id: str) -> Dict[str, Any]:
        """列出工作空间中的文件"""
        workspace = self._workspaces.get(workspace_id)
        
        if not workspace:
            return {"success": False, "error": f"工作空间不存在: {workspace_id}"}
        
        files = self._list_files(workspace["path"])
        
        return {"success": True, "files": files, "count": len(files)}
    
    def _list_files(self, workspace_path: str) -> List[Dict]:
        """列出目录中的文件"""
        files = []
        base_path = Path(workspace_path)
        
        try:
            for item in base_path.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(base_path)
                    files.append({
                        "path": str(rel_path),
                        "name": item.name,
                        "size": item.stat().st_size,
                        "modified_at": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                    })
        except Exception as e:
            logger.warning(f"列出文件失败: {e}")
        
        return files
    
    def delete_file(self, 
                    workspace_id: str,
                    file_path: str) -> Dict[str, Any]:
        """删除文件"""
        workspace = self._workspaces.get(workspace_id)
        
        if not workspace:
            return {"success": False, "error": f"工作空间不存在: {workspace_id}"}
        
        try:
            full_path = Path(workspace["path"]) / file_path
            
            if not full_path.exists():
                return {"success": False, "error": f"文件不存在: {file_path}"}
            
            full_path.unlink()
            
            workspace["modified_at"] = datetime.now().isoformat()
            
            logger.info(f"文件已删除: {workspace_id}/{file_path}")
            return {"success": True, "message": f"文件 {file_path} 已删除"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_directory(self, 
                         workspace_id: str,
                         dir_path: str) -> Dict[str, Any]:
        """创建目录"""
        workspace = self._workspaces.get(workspace_id)
        
        if not workspace:
            return {"success": False, "error": f"工作空间不存在: {workspace_id}"}
        
        try:
            full_path = Path(workspace["path"]) / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            
            workspace["modified_at"] = datetime.now().isoformat()
            
            logger.info(f"目录创建成功: {workspace_id}/{dir_path}")
            return {"success": True, "message": f"目录 {dir_path} 已创建"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_directory_tree(self, workspace_id: str) -> Dict[str, Any]:
        """获取目录树"""
        workspace = self._workspaces.get(workspace_id)
        
        if not workspace:
            return {"success": False, "error": f"工作空间不存在: {workspace_id}"}
        
        try:
            tree = self._build_tree(Path(workspace["path"]))
            
            return {"success": True, "tree": tree}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _build_tree(self, path: Path, depth: int = 0) -> Dict:
        """构建目录树"""
        if depth > 5:
            return {"name": path.name, "type": "directory", "children": []}
        
        result = {
            "name": path.name,
            "type": "directory" if path.is_dir() else "file",
            "path": str(path),
        }
        
        if path.is_dir():
            children = []
            for item in sorted(path.iterdir()):
                children.append(self._build_tree(item, depth + 1))
            result["children"] = children
        
        return result
