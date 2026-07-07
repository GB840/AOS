import json
import asyncio
from typing import Dict, Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="DesktopWorker", version="1.0.0")

class ExecuteRequest(BaseModel):
    action: str
    params: Dict[str, Any] = None

class ExecuteResponse(BaseModel):
    success: bool
    output: str = None
    data: Dict[str, Any] = None
    error: str = None

@app.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest):
    try:
        if request.action == "click":
            result = click(request.params)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "type":
            result = type_text(request.params)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "open_app":
            result = open_app(request.params)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "close_app":
            result = close_app(request.params)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "read_screen":
            result = read_screen(request.params)
            return ExecuteResponse(success=True, data=result)
        elif request.action == "get_windows":
            result = get_windows(request.params)
            return ExecuteResponse(success=True, data=result)
        elif request.action == "switch_window":
            result = switch_window(request.params)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "move_mouse":
            result = move_mouse(request.params)
            return ExecuteResponse(success=True, output=result)
        elif request.action == "scroll":
            result = scroll(request.params)
            return ExecuteResponse(success=True, output=result)
        else:
            return ExecuteResponse(success=False, error=f"Unknown action: {request.action}")
    except Exception as e:
        return ExecuteResponse(success=False, error=str(e))

def click(params: Dict[str, Any]) -> str:
    import pyautogui
    x = params.get("x", 0)
    y = params.get("y", 0)
    button = params.get("button", "left")
    clicks = params.get("clicks", 1)
    
    pyautogui.click(x=x, y=y, button=button, clicks=clicks)
    return f"Clicked at ({x}, {y}) with {button} button"

def type_text(params: Dict[str, Any]) -> str:
    import pyautogui
    text = params.get("text", "")
    interval = params.get("interval", 0.05)
    
    pyautogui.typewrite(text, interval=interval)
    return f"Typed: {text}"

def open_app(params: Dict[str, Any]) -> str:
    import subprocess
    app_path = params.get("path", "")
    app_name = params.get("name", "")
    
    if app_path:
        subprocess.Popen(app_path)
        return f"Opened app: {app_path}"
    elif app_name:
        try:
            subprocess.Popen(app_name)
            return f"Opened app: {app_name}"
        except:
            return f"Failed to open app: {app_name}"
    return "No app path or name provided"

def close_app(params: Dict[str, Any]) -> str:
    import subprocess
    app_name = params.get("name", "")
    
    if app_name:
        subprocess.run(f"taskkill /f /im {app_name}", shell=True, capture_output=True)
        return f"Closed app: {app_name}"
    return "No app name provided"

def read_screen(params: Dict[str, Any]) -> Dict[str, Any]:
    import pyautogui
    import numpy as np
    
    screenshot = pyautogui.screenshot()
    screenshot_np = np.array(screenshot)
    
    return {
        "width": screenshot.width,
        "height": screenshot.height,
        "mode": screenshot.mode,
        "pixel_count": screenshot.width * screenshot.height
    }

def get_windows(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        return {
            "count": len(windows),
            "windows": [
                {"title": w.title, "width": w.width, "height": w.height, "left": w.left, "top": w.top}
                for w in windows
            ]
        }
    except ImportError:
        return {"error": "pygetwindow not installed", "windows": []}

def switch_window(params: Dict[str, Any]) -> str:
    try:
        import pygetwindow as gw
        title = params.get("title", "")
        windows = gw.getWindowsWithTitle(title)
        if windows:
            windows[0].activate()
            return f"Switched to window: {title}"
        return f"No window found with title: {title}"
    except ImportError:
        return "pygetwindow not installed"

def move_mouse(params: Dict[str, Any]) -> str:
    import pyautogui
    x = params.get("x", 0)
    y = params.get("y", 0)
    duration = params.get("duration", 0.25)
    
    pyautogui.moveTo(x, y, duration=duration)
    return f"Moved mouse to ({x}, {y})"

def scroll(params: Dict[str, Any]) -> str:
    import pyautogui
    clicks = params.get("clicks", 10)
    direction = params.get("direction", "up")
    
    pyautogui.scroll(clicks=clicks, direction=direction)
    return f"Scrolled {direction} by {clicks} clicks"

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "DesktopWorker"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)