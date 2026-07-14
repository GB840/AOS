"""
Jina Reader Skill Module - 网页正文提取

Jina Reader 是一个网页正文提取服务，将任意URL转换为干净的Markdown或JSON。
核心价值：免费额度非常慷慨，无API Key时20次/分钟，注册后可获1000万Token免费额度。

技术特点:
- 支持任意URL提取
- 输出格式：Markdown、JSON
- 自动清理广告和无关内容
- 支持提取全文、摘要、标题
- 免费额度充足

使用方式:
- 无需安装，直接通过URL前缀调用
- https://r.jina.ai/http://目标网址
- 支持本地降级：使用 requests + BeautifulSoup
"""

import json
import logging
import uuid
import requests
from typing import Dict, List, Any
from datetime import datetime
from urllib.parse import urlparse

from .base import Skill
from utils.config import config

logger = logging.getLogger(__name__)

READER_FORMATS = {
    "markdown": {"name": "Markdown", "description": "输出Markdown格式"},
    "json": {"name": "JSON", "description": "输出JSON格式"},
    "text": {"name": "纯文本", "description": "输出纯文本格式"},
}

READER_FEATURES = {
    "extract": {"name": "正文提取", "description": "提取网页正文内容"},
    "summary": {"name": "摘要生成", "description": "生成网页摘要"},
    "full": {"name": "完整提取", "description": "提取完整页面信息"},
    "batch": {"name": "批量提取", "description": "批量提取多个URL"},
    "validate": {"name": "URL验证", "description": "验证URL是否可访问"},
}


class JinaReaderSkill(Skill):
    """
    Jina Reader 网页正文提取技能
    
    提供网页正文提取能力，支持多种输出格式和提取模式。
    使用 Jina Reader API，免费额度充足。
    当 Jina Reader 不可用时，自动降级到本地提取方案。
    """
    
    NAME = "jina_reader"
    DESCRIPTION = "Jina Reader 网页正文提取 — 将任意URL转换为干净的Markdown或JSON，免费额度充足"
    VERSION = "1.1.0"
    AUTHOR = "Jina AI"
    LICENSE = "Apache-2.0"
    CATEGORY = "web"
    TAGS = ["web", "reader", "jina", "extract", "scraping"]
    CAPABILITIES = ["web_extract", "content_cleaning", "summary_generation", "batch_extract", "url_validation"]
    
    def __init__(self):
        super().__init__()
        self._reader_url = getattr(config, "JINA_READER_URL", "https://r.jina.ai")
        self._api_url = getattr(config, "JINA_API_URL", "https://api.jina.ai/v1/extract")
        self._api_key = getattr(config, "JINA_API_KEY", "")
        self._enhanced_mode = True
        self._use_local_fallback = True
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def close(self) -> None:
        """释放底层连接池，避免 Session 长期持有 socket。"""
        sess = getattr(self, "_session", None)
        if sess is not None:
            try:
                sess.close()
            except Exception:
                pass

    def __del__(self):
        self.close()

    def __enter__(self) -> "JinaReaderSkill":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行网页提取任务
        
        Args:
            context: 执行上下文
                - action: 操作类型 (extract/summary/full/batch/validate)
                - url: 目标URL（必填）
                - format: 输出格式（可选，默认markdown）
                - urls: URL列表（批量提取时使用）
        
        Returns:
            Dict: 提取结果
        """
        action = context.get("action", "extract")
        url = context.get("url", context.get("input", ""))
        
        if action not in READER_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(READER_FEATURES.keys())}",
                "available_actions": READER_FEATURES,
            }
        
        if not url and action != "batch":
            return {
                "success": False,
                "error": "缺少 url 参数",
            }
        
        task_id = str(uuid.uuid4())[:8]
        output_format = context.get("format", "markdown")
        
        if self._enhanced_mode:
            result = self._execute_enhanced(action, url, output_format, context)
            if not result.get("success") and self._use_local_fallback:
                logger.info("Jina Reader失败，切换到本地提取")
                result = self._execute_local(action, url, output_format, context)
        else:
            result = self._execute_local(action, url, output_format, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": READER_FEATURES[action]["name"],
            "url": url,
            "format": output_format,
            "result": result.get("result"),
            "error": result.get("error"),
            "mode": result.get("mode", "enhanced"),
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_enhanced(self, action: str, url: str, output_format: str, context: Dict) -> Dict[str, Any]:
        """增强模式执行 — 使用 Jina Reader URL前缀"""
        try:
            if action == "extract" or action == "full":
                return self._extract_url_jina(url, output_format)
            elif action == "summary":
                return self._extract_summary(url)
            elif action == "batch":
                urls = context.get("urls", [])
                return self._batch_extract(urls, output_format)
            elif action == "validate":
                return self._validate_url(url)
            else:
                return {"success": False, "error": f"未知操作: {action}"}
        except Exception as e:
            logger.error(f"增强模式提取失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _execute_local(self, action: str, url: str, output_format: str, context: Dict) -> Dict[str, Any]:
        """本地模式执行 — 使用 requests + BeautifulSoup"""
        try:
            if action == "extract" or action == "full":
                return self._extract_url_local(url, output_format)
            elif action == "summary":
                return self._extract_summary_local(url)
            elif action == "batch":
                urls = context.get("urls", [])
                return self._batch_extract_local(urls, output_format)
            elif action == "validate":
                return self._validate_url(url)
            else:
                return {"success": False, "error": f"未知操作: {action}"}
        except Exception as e:
            logger.error(f"本地模式提取失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _extract_url_jina(self, url: str, output_format: str) -> Dict[str, Any]:
        """使用 Jina Reader 提取网页正文"""
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme if parsed.scheme else "https"
            clean_url = f"{scheme}://{parsed.netloc}{parsed.path}"
            
            reader_url = f"{self._reader_url}/{clean_url}"
            
            response = self._session.get(reader_url, timeout=30, allow_redirects=True)
            
            if response.status_code == 200:
                content = response.text
                
                if output_format == "json":
                    try:
                        data = json.loads(content)
                        return {"success": True, "result": data, "mode": "jina"}
                    except json.JSONDecodeError:
                        return {"success": True, "result": {"content": content}, "mode": "jina"}
                elif output_format == "text":
                    import re
                    text = re.sub(r'#+\s', '', content)
                    text = re.sub(r'\*\*', '', text)
                    text = re.sub(r'\n{2,}', '\n', text)
                    return {"success": True, "result": text.strip(), "mode": "jina"}
                else:
                    return {"success": True, "result": content, "mode": "jina"}
            else:
                return {"success": False, "error": f"Jina Reader返回错误: {response.status_code}"}
        except Exception as e:
            logger.error(f"Jina Reader提取URL失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_url_local(self, url: str, output_format: str) -> Dict[str, Any]:
        """使用本地方法提取网页正文"""
        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                url = f"https://{url}"
            
            response = self._session.get(url, timeout=30, allow_redirects=True)
            response.encoding = response.apparent_encoding
            
            if response.status_code != 200:
                return {"success": False, "error": f"HTTP错误: {response.status_code}"}
            
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "html.parser")
                
                for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
                    tag.decompose()
                
                title = soup.title.string.strip() if soup.title else "无标题"
                
                content_divs = soup.find_all(["article", "div", "section"])
                best_content = ""
                max_length = 0
                
                for div in content_divs:
                    text = div.get_text(separator="\n", strip=True)
                    if len(text) > max_length and len(text) > 100:
                        max_length = len(text)
                        best_content = text
                
                if not best_content:
                    best_content = soup.get_text(separator="\n", strip=True)
                
                content = best_content[:5000]
                
                if output_format == "json":
                    result = {
                        "title": title,
                        "url": url,
                        "content": content,
                        "length": len(content),
                        "mode": "local",
                    }
                    return {"success": True, "result": result, "mode": "local"}
                elif output_format == "text":
                    return {"success": True, "result": content, "mode": "local"}
                else:
                    markdown = f"# {title}\n\n{content}"
                    return {"success": True, "result": markdown, "mode": "local"}
                    
            except ImportError:
                content = response.text[:10000]
                if output_format == "json":
                    return {"success": True, "result": {"content": content}, "mode": "local"}
                return {"success": True, "result": content, "mode": "local"}
                
        except Exception as e:
            logger.error(f"本地提取URL失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_summary(self, url: str) -> Dict[str, Any]:
        """提取网页摘要（优先使用Jina）"""
        try:
            extract_result = self._extract_url_jina(url, "markdown")
            
            if extract_result.get("success"):
                content = extract_result.get("result", "")
                return self._generate_summary(url, content, "jina")
            
            if self._use_local_fallback:
                extract_result = self._extract_url_local(url, "markdown")
                if extract_result.get("success"):
                    content = extract_result.get("result", "")
                    return self._generate_summary(url, content, "local")
            
            return extract_result
        except Exception as e:
            logger.error(f"提取摘要失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_summary_local(self, url: str) -> Dict[str, Any]:
        """使用本地方法提取网页摘要"""
        try:
            extract_result = self._extract_url_local(url, "markdown")
            
            if extract_result.get("success"):
                content = extract_result.get("result", "")
                return self._generate_summary(url, content, "local")
            
            return extract_result
        except Exception as e:
            logger.error(f"本地提取摘要失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _generate_summary(self, url: str, content: str, source_mode: str) -> Dict[str, Any]:
        """生成网页摘要"""
        try:
            from core import get_brain
            brain = get_brain()
            
            prompt = f"""请为以下网页内容生成摘要：

URL: {url}

内容:
{content[:3000]}

要求:
1. 提取主要内容和关键点
2. 保持简洁，不超过300字
3. 使用中文输出"""
            
            summary = brain.chat(message=prompt, session_id=f"jina-summary-{url[:20]}")
            
            return {
                "success": True,
                "result": {
                    "url": url,
                    "summary": summary.get("response", ""),
                    "source_length": len(content),
                    "mode": source_mode,
                },
            }
        except Exception as e:
            logger.error(f"生成摘要失败: {e}")
            
            import re
            sentences = re.split(r'[。！？.!?]', content)
            summary_text = "。".join(sentences[:5]) + "。" if sentences else content[:200]
            
            return {
                "success": True,
                "result": {
                    "url": url,
                    "summary": summary_text,
                    "source_length": len(content),
                    "mode": f"{source_mode}_local_summary",
                },
            }
    
    def _batch_extract(self, urls: List[str], output_format: str) -> Dict[str, Any]:
        """批量提取多个URL（优先使用Jina）"""
        results = []
        
        for url in urls[:10]:
            result = self._extract_url_jina(url, output_format)
            if not result.get("success") and self._use_local_fallback:
                result = self._extract_url_local(url, output_format)
            results.append({
                "url": url,
                "success": result.get("success", False),
                "result": result.get("result"),
                "error": result.get("error"),
                "mode": result.get("mode", "unknown"),
            })
        
        success_count = sum(1 for r in results if r["success"])
        
        return {
            "success": True,
            "result": {
                "results": results,
                "total": len(urls),
                "success_count": success_count,
                "failed_count": len(urls) - success_count,
            },
        }
    
    def _batch_extract_local(self, urls: List[str], output_format: str) -> Dict[str, Any]:
        """批量提取多个URL（本地模式）"""
        results = []
        
        for url in urls[:10]:
            result = self._extract_url_local(url, output_format)
            results.append({
                "url": url,
                "success": result.get("success", False),
                "result": result.get("result"),
                "error": result.get("error"),
                "mode": "local",
            })
        
        success_count = sum(1 for r in results if r["success"])
        
        return {
            "success": True,
            "result": {
                "results": results,
                "total": len(urls),
                "success_count": success_count,
                "failed_count": len(urls) - success_count,
            },
        }
    
    def _validate_url(self, url: str) -> Dict[str, Any]:
        """验证URL是否可访问"""
        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                url = f"https://{url}"
            
            response = self._session.head(url, timeout=10, allow_redirects=True)
            
            return {
                "success": True,
                "result": {
                    "url": url,
                    "valid": response.status_code < 400,
                    "status_code": response.status_code,
                    "redirect_url": response.url if response.history else None,
                },
            }
        except Exception as e:
            logger.error(f"验证URL失败: {e}")
            return {
                "success": True,
                "result": {
                    "url": url,
                    "valid": False,
                    "error": str(e),
                },
            }
    
    def list_formats(self) -> Dict[str, Any]:
        """列出所有可用格式"""
        return READER_FORMATS
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return READER_FEATURES


def get_jina_reader_skill() -> JinaReaderSkill:
    """获取或创建 Jina Reader 技能实例"""
    return JinaReaderSkill()


def register_jina_reader_skill(registry=None):
    """注册 Jina Reader 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = JinaReaderSkill()
    registry.register(skill)
    logger.info("Jina Reader 技能已注册")
    return skill