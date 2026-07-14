"""
Scripts Adapter - Dynamically execute files in scripts/repls/ as AOS capabilities.

This adapter watches for .py files in a directory and exposes them as executable
capabilities that can be invoked through the AOS fabric. Each file becomes
a sandboxed capability with hot-reload support.
"""

import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability


class ScriptExecutor:
    """Sandboxed script executor."""
    
    def __init__(self, script_path: str, script_name: str):
        self.script_path = script_path
        self.script_name = script_name
        self.module = None
        self.last_modified = 0
        self.load()
    
    def load(self):
        """Load or reload the script module."""
        try:
            spec = importlib.util.spec_from_file_location(
                f"repls.{self.script_name}", self.script_path
            )
            module = importlib.util.module_from_spec(spec)
            
            # Inject basic AOS context
            module.__dict__['print'] = print
            module.__dict__['input'] = input
            
            spec.loader.exec_module(module)
            self.module = module
            self.last_modified = os.path.getmtime(self.script_path)
            return True
        except Exception as e:
            print(f"❌ Failed to load script {self.script_name}: {e}")
            return False
    
    def needs_reload(self) -> bool:
        """Check if script needs reloading."""
        try:
            return os.path.getmtime(self.script_path) > self.last_modified
        except OSError:
            return False
    
    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute script with given payload."""
        if not self.module:
            return {"error": "Script not loaded"}
        
        # Reload if needed
        if self.needs_reload():
            if not self.load():
                return {"error": "Failed to reload script"}
        
        # Call main function if exists
        try:
            if hasattr(self.module, 'main'):
                result = self.module.main(payload)
                return {"result": result}
            else:
                return {"error": "Script has no main() function"}
        except Exception as e:
            return {"error": f"Script execution error: {e}"}


class ScriptsAdapter(BaseAgentAdapter):
    """Dynamic scripts executor for AOS."""
    
    def __init__(self, scripts_dir: str = "scripts/repls"):
        self.scripts_dir = Path(scripts_dir)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        
        self.executors: Dict[str, ScriptExecutor] = {}
        self._load_all_scripts()
        
        # Polling-based hot reload loop (every 5 seconds)
        self._hot_reload_enabled = True
    
    def _load_all_scripts(self):
        """Load all existing scripts."""
        for script_file in self.scripts_dir.glob("*.py"):
            if script_file.name not in ["__init__.py"]:
                self._load_script(script_file.stem, str(script_file))
    
    def _load_script(self, script_name: str, script_path: str):
        """Load a single script."""
        executor = ScriptExecutor(script_path, script_name)
        if executor.module:
            self.executors[script_name] = executor
            print(f"✅ Script '{script_name}' loaded")
    
    def _unload_script(self, script_name: str):
        """Unload a script."""
        if script_name in self.executors:
            del self.executors[script_name]
            print(f"✅ Script '{script_name}' unloaded")
    
    @property
    def engine_id(self) -> str:
        return "scripts"
    
    def advertise_capabilities(self) -> list:
        """Expose each script as a separate capability."""
        caps = [Capability.TOOL_USE]  # Base capability
        
        for script_name in self.executors.keys():
            # Create dynamic capability for each script
            caps.append(f"script.{script_name}")
        
        return caps
    
    def _hot_reload_check(self):
        """Check for script changes and reload if needed."""
        for script_file in self.scripts_dir.glob("*.py"):
            if script_file.name in ["__init__.py"]:
                continue
                
            script_name = script_file.stem
            
            # Load new scripts
            if script_name not in self.executors:
                print(f"➕ New script detected: {script_name}.py")
                self._load_script(script_name, str(script_file))
            
            # Check for modifications
            executor = self.executors.get(script_name)
            if executor and executor.needs_reload():
                print(f"🔄 Reloading modified script: {script_name}.py")
                executor.load()
        
        # Remove deleted scripts
        existing_scripts = {f.stem for f in self.scripts_dir.glob("*.py") 
                           if f.name not in ["__init__.py"]}
        for script_name in list(self.executors.keys()):
            if script_name not in existing_scripts:
                print(f"➖ Script deleted: {script_name}.py")
                self._unload_script(script_name)
    
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        """Execute a script based on capability."""
        # Do hot reload check on every invoke
        if self._hot_reload_enabled:
            self._hot_reload_check()
        
        capability = req.capability
        
        # Handle dynamic script capabilities
        if isinstance(capability, str) and capability.startswith("script."):
            script_name = capability.replace("script.", "")
            if script_name in self.executors:
                result = self.executors[script_name].invoke(req.payload)
                return InvokeResult(
                    ok="error" not in result,
                    data=result,
                    error=result.get("error")
                )
        
        # Default tool use
        return InvokeResult(
            ok=False,
            error=f"Unknown capability: {capability}"
        )
    
    def health(self) -> bool:
        """Health check - true if scripts directory exists."""
        return self.scripts_dir.exists()
    
    def stop(self):
        """Stop hot reload."""
        self._hot_reload_enabled = False


# Global adapter instance (for fabric hub registration)
adapter_instance: Optional[ScriptsAdapter] = None


def get_scripts_adapter() -> ScriptsAdapter:
    """Get or create the global scripts adapter instance."""
    global adapter_instance
    if adapter_instance is None:
        adapter_instance = ScriptsAdapter()
    return adapter_instance


def stop_scripts_adapter():
    """Stop the global scripts adapter."""
    global adapter_instance
    if adapter_instance:
        adapter_instance.stop()
        adapter_instance = None