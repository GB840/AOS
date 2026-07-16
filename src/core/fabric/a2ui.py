"""A2UI 协议（v0.9，https://a2ui.org）在 AOS 的落地。

让 AOS 的 agent（含编排芯粒 / ag2 规划产物）能**发出声明式、流式 UI 规范**
（createSurface / updateComponents / updateDataModel / deleteSurface），
任何 A2UI 客户端用原生组件渲染——**不执行代码、不注入 HTML**，跨信任边界也安全。

本模块同时提供一个**纯标准库 HTML 渲染器** `render_html`，让 AOS 自己的 Web
前端今天就能把 A2UI 表面渲染出来（无需引入 Angular/Flutter/React）。

设计对齐 autogen/ag2 的 `A2UIAgent`（v0.9 basic catalog），因此将来 ag2
规划器产出的 A2UI 可直接被本渲染器消费。

安全模型（与 A2UI 规范一致）：
  - 仅渲染 `KNOWN_COMPONENTS` 白名单内的组件；未知组件被丢弃（catalog 强制）。
  - 所有文本经 `html.escape` 转义；不构造 `<script>`、不 `eval`。
  - Image/Video/Audio 的 url 仅允许 http/https/相对路径，拦截 `javascript:`、
    `data:`（除 `data:image/*;base64` 显式白名单外）等危险 scheme。
"""
from __future__ import annotations

import html
import json
import sys
from typing import Any, Dict, List, Optional

__all__ = [
    "VERSION", "CATALOG_ID", "KNOWN_COMPONENTS",
    "lit", "ref",
    "A2UIBuilder",
    "render_html", "render_a2ui",
    "build_a2ui_report",
    "validate_surface",
]

VERSION = "v0.9"
CATALOG_ID = "https://a2ui.org/specification/v0_9/basic_catalog.json"

# v0.9 basic catalog 的 18 个组件（白名单，渲染器只认这些）
KNOWN_COMPONENTS = frozenset({
    "Text", "Image", "Icon", "Video", "AudioPlayer",
    "Row", "Column", "List", "Card", "Tabs", "Modal", "Divider",
    "Button", "TextField", "CheckBox", "ChoicePicker", "Slider", "DateTimeInput",
})


# ─── DynamicString / 数据绑定 ──────────────────────────────────────

def lit(value: str) -> Dict[str, Any]:
    """字面量字符串绑定。"""
    return {"literalString": str(value)}


def ref(path: str) -> Dict[str, Any]:
    """指向数据模型某路径（JSON Pointer 风格，如 '/user/name'）。"""
    return {"path": path}


def _resolve_dynamic(dyn: Any, data_model: Dict[str, Any]) -> str:
    """把 DynamicString（literal/path/functionCall）解析为展示字符串。

    函数调用（functionCall）是客户端能力，服务端**不执行**——仅尽力回退为
    字面量（若有），否则空串。这样保证零代码执行、零注入。
    """
    if isinstance(dyn, dict):
        if "literalString" in dyn:
            return str(dyn["literalString"])
        if "path" in dyn:
            return _get_path(data_model, dyn["path"])
        # functionCall / 其他：不执行，返回空（安全优先）
        return ""
    if dyn is None:
        return ""
    return str(dyn)


def _get_path(model: Dict[str, Any], pointer: str) -> str:
    """极简 JSON Pointer 取值（仅支持 /a/b/c 字典链）。"""
    if not isinstance(model, dict):
        return ""
    cur: Any = model
    for part in [p for p in pointer.split("/") if p]:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return ""
    return str(cur) if cur is not None else ""


# ─── 组件构造（每个返回 {component:"X", ...} 字典，不含 id）─────────

def _mk(kind: str, **props: Any) -> Dict[str, Any]:
    if kind not in KNOWN_COMPONENTS:
        raise ValueError(f"未知 A2UI 组件类型: {kind!r}（不在 basic catalog 白名单）")
    comp: Dict[str, Any] = {"component": kind}
    comp.update(props)
    return comp


def text(content: Any, variant: str = "body") -> Dict[str, Any]:
    return _mk("Text", text=content, variant=variant)


def button(child_id: str, action: Optional[Dict[str, Any]] = None,
           variant: str = "default") -> Dict[str, Any]:
    comp = _mk("Button", child=child_id, variant=variant)
    if action is not None:
        comp["action"] = action
    return comp


def text_field(label: Any, value: Any = None, variant: str = "shortText",
               validation_regexp: Optional[str] = None) -> Dict[str, Any]:
    comp = _mk("TextField", label=label, variant=variant)
    if value is not None:
        comp["value"] = value
    if validation_regexp is not None:
        comp["validationRegexp"] = validation_regexp
    return comp


def card(child_id: str) -> Dict[str, Any]:
    return _mk("Card", child=child_id)


def column(children: List[str], justify: str = "start",
           align: str = "stretch") -> Dict[str, Any]:
    return _mk("Column", children=list(children), justify=justify, align=align)


def row(children: List[str], justify: str = "start",
        align: str = "stretch") -> Dict[str, Any]:
    return _mk("Row", children=list(children), justify=justify, align=align)


def list_cmp(children: List[str], direction: str = "vertical") -> Dict[str, Any]:
    return _mk("List", children=list(children), direction=direction)


def image(url: Any, fit: str = "fill", variant: str = "mediumFeature") -> Dict[str, Any]:
    return _mk("Image", url=url, fit=fit, variant=variant)


def divider(axis: str = "horizontal") -> Dict[str, Any]:
    return _mk("Divider", axis=axis)


def checkbox(label: Any, value: bool = False) -> Dict[str, Any]:
    return _mk("CheckBox", label=label, value=bool(value))


def choice_picker(label: Any, options: List[Dict[str, str]],
                  value: Optional[List[str]] = None,
                  variant: str = "mutuallyExclusive") -> Dict[str, Any]:
    comp = _mk("ChoicePicker", label=label, options=list(options), variant=variant)
    if value is not None:
        comp["value"] = list(value)
    return comp


def slider(label: Any, value: float, max: float, min: float = 0) -> Dict[str, Any]:
    return _mk("Slider", label=label, value=value, max=max, min=min)


def datetime_input(value: str = "", enable_date: bool = False,
                   enable_time: bool = False, label: Any = None) -> Dict[str, Any]:
    comp = _mk("DateTimeInput", value=value, enableDate=enable_date,
               enableTime=enable_time)
    if label is not None:
        comp["label"] = label
    return comp


def tabs(tabs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """tabs: [{"title": DynamicString, "child": componentId}, ...]"""
    return _mk("Tabs", tabs=list(tabs))


def modal(trigger_id: str, content_id: str) -> Dict[str, Any]:
    return _mk("Modal", trigger=trigger_id, content=content_id)


def icon(name: str) -> Dict[str, Any]:
    return _mk("Icon", name=name)


def video(url: Any) -> Dict[str, Any]:
    return _mk("Video", url=url)


def audio(url: Any, description: Any = None) -> Dict[str, Any]:
    comp = _mk("AudioPlayer", url=url)
    if description is not None:
        comp["description"] = description
    return comp


# ─── 构建器 ────────────────────────────────────────────────────────

class A2UIBuilder:
    """累积组件 + 数据模型，产出 v0.9 信封消息或合并 surface（供渲染）。"""

    def __init__(self, surface_id: str = "main",
                 catalog_id: str = CATALOG_ID, theme: Optional[Dict[str, Any]] = None) -> None:
        self.surface_id = surface_id
        self.catalog_id = catalog_id
        self.theme = theme
        self._components: Dict[str, Dict[str, Any]] = {}
        self._root: Optional[str] = None
        self._data_model: Dict[str, Any] = {}

    def add(self, cid: str, comp: Dict[str, Any]) -> "A2UIBuilder":
        if "component" not in comp:
            raise ValueError(f"组件 {cid!r} 缺少 'component' 字段")
        if comp["component"] not in KNOWN_COMPONENTS:
            raise ValueError(f"组件 {cid!r} 类型 {comp['component']!r} 不在白名单")
        self._components[cid] = comp
        return self

    def root(self, cid: str) -> "A2UIBuilder":
        self._root = cid
        return self

    def set_data(self, path: str, value: Any) -> "A2UIBuilder":
        # 支持 '/a/b' 嵌套写入
        parts = [p for p in path.split("/") if p]
        node = self._data_model
        for p in parts[:-1]:
            node = node.setdefault(p, {})
            if not isinstance(node, dict):
                raise ValueError(f"数据模型路径冲突: {path}")
        node[parts[-1]] = value
        return self

    def create_surface(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {
            "version": VERSION,
            "createSurface": {"surfaceId": self.surface_id, "catalogId": self.catalog_id},
        }
        if self.theme:
            msg["createSurface"]["theme"] = self.theme
        return msg

    def update_components(self) -> Dict[str, Any]:
        if self._root is None:
            raise ValueError("未设置 root 组件（updateComponents 需要 id='root'）")
        components = [{"id": cid, "component": comp}
                      for cid, comp in self._components.items()]
        # 确保 root 在列表里（结构要求至少一个 id='root'）
        if "root" not in self._components:
            components.append({"id": "root", "component": self._components[self._root]})
        return {
            "version": VERSION,
            "updateComponents": {"surfaceId": self.surface_id, "components": components},
        }

    def update_data_model(self) -> List[Dict[str, Any]]:
        msgs = []
        for path, value in self._data_model.items():
            msgs.append({
                "version": VERSION,
                "updateDataModel": {
                    "surfaceId": self.surface_id,
                    "path": "/" + path,
                    "value": value,
                },
            })
        return msgs

    def delete_surface(self) -> Dict[str, Any]:
        return {
            "version": VERSION,
            "deleteSurface": {"surfaceId": self.surface_id},
        }

    def messages(self, include_delete: bool = False) -> List[Dict[str, Any]]:
        """产出发送顺序的信封消息列表。"""
        out: List[Dict[str, Any]] = [self.create_surface(), self.update_components()]
        out.extend(self.update_data_model())
        if include_delete:
            out.append(self.delete_surface())
        return out

    def surface(self) -> Dict[str, Any]:
        """合并为单一 surface 对象（供渲染器消费，也便于存储/传输）。"""
        if self._root is None:
            raise ValueError("未设置 root 组件")
        root_id = "root" if "root" in self._components else self._root
        components = dict(self._components)
        if root_id == "root" and self._root not in ("root",):
            components = {**self._components, "root": self._components[self._root]}
        return {
            "surfaceId": self.surface_id,
            "catalogId": self.catalog_id,
            "theme": self.theme,
            "root": root_id,
            "components": components,
            "dataModel": self._data_model,
        }


# ─── 校验 ──────────────────────────────────────────────────────────

def validate_surface(surface: Dict[str, Any]) -> List[str]:
    """返回错误列表（空=合法）。"""
    errors: List[str] = []
    if not isinstance(surface, dict):
        return ["surface 必须是对象"]
    if "surfaceId" not in surface:
        errors.append("缺少 surfaceId")
    if "root" not in surface:
        errors.append("缺少 root")
    comps = surface.get("components")
    if not isinstance(comps, dict) or not comps:
        errors.append("components 必须是非空对象")
        return errors
    if surface.get("root") not in comps:
        errors.append(f"root 组件 {surface.get('root')!r} 不在 components 中")
    for cid, comp in comps.items():
        if not isinstance(comp, dict) or "component" not in comp:
            errors.append(f"组件 {cid!r} 结构非法")
            continue
        if comp["component"] not in KNOWN_COMPONENTS:
            errors.append(f"组件 {cid!r} 类型 {comp['component']!r} 不在白名单")
    return errors


# ─── 安全渲染器（纯标准库 HTML）────────────────────────────────────

_ALLOWED_URL_PREFIXES = ("http://", "https://", "/", "./", "../")


def _safe_url(url: str) -> Optional[str]:
    """仅放行 http/https/相对路径；拦截 javascript:/data: 等危险 scheme。"""
    if not isinstance(url, str):
        return None
    u = url.strip()
    low = u.lower()
    if any(low.startswith(p) for p in _ALLOWED_URL_PREFIXES):
        return u
    # 显式白名单：data:image/*;base64（常见内嵌小图，非脚本）
    if low.startswith("data:image/") and ";base64," in low:
        return u
    return None


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _render_component(cid: str, surface: Dict[str, Any],
                      seen: Optional[set] = None) -> str:
    """递归渲染单个组件为 HTML 片段。"""
    comps = surface.get("components", {})
    comp = comps.get(cid)
    if comp is None:
        return ""
    kind = comp.get("component")
    if kind not in KNOWN_COMPONENTS:
        # catalog 强制：未知组件丢弃，不渲染
        return ""
    dm = surface.get("dataModel", {}) or {}

    # 防止环形引用导致无限递归
    seen = seen or set()
    if cid in seen:
        return ""
    seen = seen | {cid}

    if kind == "Text":
        variant = comp.get("variant", "body")
        txt = _esc(_resolve_dynamic(comp.get("text"), dm))
        tag = {"h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h5",
               "caption": "small", "body": "p"}.get(variant, "p")
        return f"<{tag} class='a2ui-text'>{txt}</{tag}>"

    if kind == "Divider":
        return "<hr class='a2ui-divider'/>"

    if kind == "Image":
        url = _safe_url(_resolve_dynamic(comp.get("url"), dm))
        if not url:
            return "<div class='a2ui-img a2ui-broken'>[图片 URL 被拦截]</div>"
        return f"<img class='a2ui-img' src='{_esc(url)}' alt='image'/>"

    if kind == "Video":
        url = _safe_url(_resolve_dynamic(comp.get("url"), dm))
        if not url:
            return "<div class='a2ui-broken'>[视频 URL 被拦截]</div>"
        return (f"<video class='a2ui-video' src='{_esc(url)}' controls></video>")

    if kind == "AudioPlayer":
        url = _safe_url(_resolve_dynamic(comp.get("url"), dm))
        if not url:
            return "<div class='a2ui-broken'>[音频 URL 被拦截]</div>"
        return (f"<audio class='a2ui-audio' src='{_esc(url)}' controls></audio>")

    if kind == "Icon":
        name = comp.get("name")
        name = name if isinstance(name, str) else (name.get("path") if isinstance(name, dict) else "")
        return f"<span class='a2ui-icon' title='{_esc(name)}'>&#9881;</span>"

    if kind in ("Column", "Row", "List"):
        children = comp.get("children") or []
        inner = ""
        for child in children:
            inner += _render_component(child, surface, seen)
        cls = {"Column": "a2ui-column", "Row": "a2ui-row", "List": "a2ui-list"}[kind]
        return f"<div class='{cls}'>{inner}</div>"

    if kind == "Card":
        inner = _render_component(comp.get("child", ""), surface, seen)
        return f"<div class='a2ui-card'>{inner}</div>"

    if kind == "Tabs":
        # 安全优先：不引入交互 JS，按标题堆叠渲染（静态、可读）
        blocks = ""
        for t in comp.get("tabs", []):
            title = _esc(_resolve_dynamic(t.get("title"), dm))
            body = _render_component(t.get("child", ""), surface, seen)
            blocks += f"<section class='a2ui-tab'><h4>{title}</h4>{body}</section>"
        return f"<div class='a2ui-tabs'>{blocks}</div>"

    if kind == "Modal":
        body = _render_component(comp.get("content", ""), surface, seen)
        return f"<div class='a2ui-modal'><strong>[模态]</strong>{body}</div>"

    if kind == "Button":
        inner = _render_component(comp.get("child", ""), surface, seen)
        variant = comp.get("variant", "default")
        # action 仅作为数据属性记录，不执行任何逻辑（安全）
        return f"<button class='a2ui-btn a2ui-btn-{_esc(variant)}' type='button'>{inner}</button>"

    if kind == "TextField":
        label = _esc(_resolve_dynamic(comp.get("label"), dm))
        val = _esc(_resolve_dynamic(comp.get("value"), dm))
        variant = comp.get("variant", "shortText")
        input_type = {"shortText": "text", "longText": "text", "number": "number",
                      "obscured": "password"}.get(variant, "text")
        return (f"<label class='a2ui-field'>{label}<br/>"
                f"<input class='a2ui-input' type='{input_type}' value='{val}'/></label>")

    if kind == "CheckBox":
        label = _esc(_resolve_dynamic(comp.get("label"), dm))
        checked = " checked" if comp.get("value") else ""
        return (f"<label class='a2ui-check'><input type='checkbox'{checked}/>"
                f"{label}</label>")

    if kind == "ChoicePicker":
        label = _esc(_resolve_dynamic(comp.get("label"), dm))
        opts = "".join(
            f"<option value='{_esc(o.get('value',''))}'>{_esc(_resolve_dynamic(o.get('label'), dm))}</option>"
            for o in comp.get("options", [])
        )
        return f"<label class='a2ui-choice'>{label}<select class='a2ui-select'>{opts}</select></label>"

    if kind == "Slider":
        label = _esc(_resolve_dynamic(comp.get("label"), dm))
        val = comp.get("value", 0)
        mx = comp.get("max", 100)
        return (f"<label class='a2ui-slider'>{label}<br/>"
                f"<input type='range' min='{_esc(comp.get('min',0))}' "
                f"max='{_esc(mx)}' value='{_esc(val)}'/></label>")

    if kind == "DateTimeInput":
        val = _esc(_resolve_dynamic(comp.get("value"), dm))
        return (f"<label class='a2ui-datetime'>"
                f"{_esc(_resolve_dynamic(comp.get('label'), dm))}<br/>"
                f"<input type='datetime-local' value='{val}'/></label>")

    return ""


def render_html(surface: Dict[str, Any], standalone: bool = False) -> str:
    """把合并 surface 渲染为安全 HTML。standalone=True 时包裹完整 HTML 文档。"""
    errors = validate_surface(surface)
    if errors:
        # 诚实失败：返回错误说明，不渲染半成品
        err_html = "".join(f"<li>{_esc(e)}</li>" for e in errors)
        body = f"<div class='a2ui-error'><strong>A2UI 校验失败:</strong><ul>{err_html}</ul></div>"
    else:
        root = surface.get("root")
        body = _render_component(root, surface)

    inner = (
        f"<div class='a2ui-surface' data-surface='{_esc(surface.get('surfaceId',''))}'>"
        f"{body}</div>"
    )
    if not standalone:
        return inner
    return (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>A2UI Surface</title>"
        "<style>"
        "body{font-family:system-ui,'Segoe UI',sans-serif;margin:0;padding:16px;"
        "background:#0f1115;color:#e6e6e6}"
        ".a2ui-surface{max-width:760px;margin:0 auto}"
        ".a2ui-card{border:1px solid #2a2f3a;border-radius:10px;padding:12px;margin:8px 0;background:#161a22}"
        ".a2ui-column{display:flex;flex-direction:column;gap:8px}"
        ".a2ui-row{display:flex;flex-direction:row;gap:8px;flex-wrap:wrap}"
        ".a2ui-list{display:flex;flex-direction:column;gap:4px}"
        ".a2ui-divider{border:none;border-top:1px solid #2a2f3a;margin:12px 0}"
        ".a2ui-btn{padding:8px 14px;border-radius:8px;border:1px solid #3a7;solid #2a8;cursor:pointer}"
        ".a2ui-btn-primary{background:#2a8;color:#fff;border-color:#2a8}"
        ".a2ui-btn-borderless{background:none;border:none;color:#6cf;text-decoration:underline}"
        ".a2ui-input,.a2ui-select{padding:6px;border-radius:6px;border:1px solid #2a2f3a;background:#0c0f14;color:#e6e6e6}"
        ".a2ui-img,.a2ui-video,.a2ui-audio{max-width:100%;border-radius:8px}"
        ".a2ui-tabs section{border-left:3px solid #2a8;padding-left:10px;margin:8px 0}"
        ".a2ui-modal{border:2px dashed #555;border-radius:10px;padding:10px;margin:8px 0}"
        ".a2ui-error{color:#f88;border:1px solid #800;padding:10px;border-radius:8px}"
        ".a2ui-broken{color:#888;font-style:italic}"
        "</style></head><body>" + inner + "</body></html>"
    )


def render_a2ui(payload: Dict[str, Any], standalone: bool = False) -> str:
    """接受合并 surface 或 {messages:[...]} 信封列表，统一渲染。"""
    if "surface" in payload and isinstance(payload["surface"], dict):
        return render_html(payload["surface"], standalone=standalone)
    if "messages" in payload and isinstance(payload["messages"], list):
        surf = _messages_to_surface(payload["messages"])
        return render_html(surf, standalone=standalone)
    if isinstance(payload, dict) and "surfaceId" in payload:
        return render_html(payload, standalone=standalone)
    raise ValueError("payload 须含 surface / messages / 或本身就是 surface 对象")


def _messages_to_surface(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把 v0.9 信封消息列表合并为 surface（取最后的组件与数据模型）。"""
    surface: Dict[str, Any] = {"components": {}, "dataModel": {}}
    for msg in messages:
        if "createSurface" in msg:
            cs = msg["createSurface"]
            surface["surfaceId"] = cs.get("surfaceId")
            surface["catalogId"] = cs.get("catalogId")
            surface["theme"] = cs.get("theme")
        elif "updateComponents" in msg:
            uc = msg["updateComponents"]
            surface["surfaceId"] = uc.get("surfaceId")
            for item in uc.get("components", []):
                cid = item.get("id")
                if cid:
                    surface["components"][cid] = item.get("component", {})
        elif "updateDataModel" in msg:
            ud = msg["updateDataModel"]
            surface["surfaceId"] = ud.get("surfaceId")
            if "value" in ud:
                surface["dataModel"][(ud.get("path") or "/").lstrip("/")] = ud["value"]
    # root：优先名为 root 的组件，否则第一个
    if "root" in surface["components"]:
        surface["root"] = "root"
    elif surface["components"]:
        surface["root"] = next(iter(surface["components"]))
    else:
        surface["root"] = None
    return surface


# ─── 编排桥接：trace -> A2UI 报告 ───────────────────────────────────

def build_a2ui_report(trace: List[Dict[str, Any]], ok_steps: int, failed_steps: int,
                      final: Any = None, title: str = "任务执行报告") -> Dict[str, Any]:
    """把编排芯粒的执行 trace 渲染成一个 A2UI 表面（agent 画界面闭环）。

    返回一个合并 surface 字典，可直接 render_html 显示。
    """
    b = A2UIBuilder(surface_id="aos-report", theme={"primaryColor": "#2a8c6a"})
    b.add("title", text(title, variant="h2"))
    b.add("summary", text(
        lit(f"成功 {ok_steps} 步 · 失败 {failed_steps} 步 · 共 {len(trace)} 步"),
        variant="caption"))
    b.add("rule", divider())

    rows: List[str] = []
    for t in trace:
        idx = t.get("step", "?")
        cap = t.get("capability") or "?"
        ok = t.get("ok", False)
        status = "✓" if ok else "✗"
        detail = ""
        if ok and isinstance(t.get("out"), (str, int, float)):
            detail = str(t.get("out"))[:80]
        elif not ok:
            detail = str(t.get("error", ""))[:80]
        cid = f"step-{idx}"
        b.add(cid, text(lit(f"{status} 步骤{idx} [{cap}] {detail}"), variant="body"))
        rows.append(cid)

    b.add("steps", list_cmp(rows) if rows else text(lit("（无步骤）")))
    if final is not None:
        fstr = final if isinstance(final, str) else json.dumps(final, ensure_ascii=False)[:200]
        b.add("final", card("final-inner"))
        b.add("final-inner", text(lit(f"最终结果: {fstr}"), variant="body"))

    b.add("root", column(["title", "summary", "rule", "steps"] +
                          (["final"] if final is not None else [])))
    b.root("root")
    return b.surface()


# ─── 命令行演示 ────────────────────────────────────────────────────

def _demo_surface() -> Dict[str, Any]:
    b = A2UIBuilder(surface_id="demo", theme={"primaryColor": "#2a8c6a"})
    b.add("h", text(lit("A2UI 演示 · AOS"), variant="h1"))
    b.add("desc", text(lit("这是 AOS 用 A2UI 协议声明式生成的界面（非 HTML 注入，安全渲染）。"),
                       variant="body"))
    b.add("name-field", text_field(lit("你的名字"), value=lit(""), variant="shortText"))
    b.add("ok-btn-label", text(lit("提交"), variant="body"))
    b.add("ok-btn", button("ok-btn-label", action={"name": "submit"}, variant="primary"))
    b.add("form", card("form-inner"))
    b.add("form-inner", column(["name-field", "ok-btn"]))
    b.add("img", image(lit("https://a2ui.org/favicon.ico")))
    b.add("root", column(["h", "desc", "form", "img"]))
    b.root("root")
    return b.surface()


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    out_path = None
    for i, a in enumerate(argv):
        if a in ("-o", "--out") and i + 1 < len(argv):
            out_path = argv[i + 1]
    surf = _demo_surface()
    html_out = render_html(surf, standalone=True)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        print(f"已写出 A2UI 演示 HTML -> {out_path}")
    else:
        print(html_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
