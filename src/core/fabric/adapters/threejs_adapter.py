"""Interactive 3D scene adapter —— AOS fabric 的 MEDIA_3D 平面。

让 AOS 从一句话生成**可交互的 3D 场景 / 小应用**（不是文本对话）。
输出是自包含的 HTML：浏览器端用 Three.js（CDN）+ OrbitControls 渲染，
用户可拖拽旋转、滚轮缩放、自动旋转 —— **交互发生在浏览器**，服务端只生成+托管。

设计原则（对齐 AOS 第一性）：
- 零服务端重依赖：只生成 HTML 字符串，不需要 GPU / Node / 浏览器在服务端。
- 云端用不了就本地：LLM 增强不可用时（无 key / 无网），回退到启发式
  「关键词→场景类型 + prompt 哈希派生调色板」生成器，保证每次都产出可交互 3D
  （诚实，不谎报 LLM 生成）。LLM 增强是干净的扩展点（见 invoke 注释）。
- 经 FabricHub 注册为 media.3d 能力，参与统一路由；也可被 OrchestrationChiplet 编排。
"""
from __future__ import annotations

import hashlib
import html as _html
import logging
import re

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)

# 浏览器端依赖的 Three.js（ESM）。CDN 挂了就提示用户联网 / 部署本地版本。
THREE_CDN = "https://unpkg.com/three@0.160.0"


def _palette(seed: str) -> list[str]:
    """从 prompt 派生的确定性调色板（同 prompt 同配色）。"""
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    return [
        "#%02x%02x%02x" % ((h >> 0) & 255, (h >> 8) & 255, (h >> 16) & 255),
        "#%02x%02x%02x" % ((h >> 8) & 255, (h >> 16) & 255, (h >> 24) & 255),
        "#%02x%02x%02x" % ((h >> 16) & 255, (h >> 24) & 255, (h >> 0) & 255),
    ]


def _scene_type(prompt: str) -> str:
    """启发式：从 prompt 选场景类型（诚实的轻量 prompt→3D 映射）。"""
    p = prompt.lower()
    if re.search(r"粒子|particle|宇宙|space|尘|银河|galaxy", p):
        return "particles"
    if re.search(r"城市|city|楼|建筑|building|街|小镇|town", p):
        return "city"
    if re.search(r"地球|earth|行星|planet|球|sphere|太阳|sun|月亮|moon", p):
        return "planet"
    if re.search(r"文字|text|字|标|title|牌|标语", p):
        return "text"
    return "knot"  # 默认：环面纽结（辨识度高、转动好看）


def _scene_js(scene_type: str, palette: list[str], prompt: str) -> str:
    """返回一段 Three.js 场景构建 JS（注入模板）。单括号为合法 JS。"""
    c0, c1, c2 = palette[0], palette[1], palette[2]
    i0, i1, i2 = int(c0[1:], 16), int(c1[1:], 16), int(c2[1:], 16)

    if scene_type == "particles":
        return (
            "const N=4000;const pos=new Float32Array(N*3);"
            "for(let i=0;i<N;i++){const r=6*Math.cbrt(Math.random());"
            "const a=Math.random()*Math.PI*2,ph=Math.acos(2*Math.random()-1);"
            "pos[i*3]=r*Math.sin(ph)*Math.cos(a);"
            "pos[i*3+1]=r*Math.sin(ph)*Math.sin(a);"
            "pos[i*3+2]=r*Math.cos(ph);}"
            "const g=new THREE.BufferGeometry();"
            "g.setAttribute('position',new THREE.BufferAttribute(pos,3));"
            "const m=new THREE.PointsMaterial({color:0x%06x,size:0.08,transparent:true,opacity:0.9});"
            "const pts=new THREE.Points(g,m);scene.add(pts);controls.target.set(0,0,0);"
            "animate=()=>{pts.rotation.y+=0.0015};"
        ) % i0

    if scene_type == "city":
        return (
            "const grp=new THREE.Group();"
            "for(let x=-4;x<=4;x++)for(let z=-4;z<=4;z++){"
            "const h=0.5+Math.random()*3.5;"
            "const b=new THREE.Mesh(new THREE.BoxGeometry(0.8,h,0.8),"
            "new THREE.MeshStandardMaterial({color:0x%06x,roughness:0.6}));"
            "b.position.set(x,h/2,z);grp.add(b);}"
            "scene.add(grp);controls.target.set(0,1.5,0);"
            "animate=()=>{grp.rotation.y+=0.001};"
        ) % i1

    if scene_type == "planet":
        return (
            "const sphere=new THREE.Mesh(new THREE.SphereGeometry(2,48,48),"
            "new THREE.MeshStandardMaterial({color:0x%06x,roughness:0.5,metalness:0.1}));"
            "const wire=new THREE.Mesh(new THREE.SphereGeometry(2.05,24,24),"
            "new THREE.MeshBasicMaterial({color:0x%06x,wireframe:true}));"
            "scene.add(sphere);scene.add(wire);controls.target.set(0,0,0);"
            "animate=()=>{sphere.rotation.y+=0.004;wire.rotation.y-=0.002};"
        ) % (i0, i2)

    if scene_type == "text":
        safe = _html.escape(prompt[:30], quote=True).replace("'", "")
        return (
            "const cv=document.createElement('canvas');cv.width=512;cv.height=128;"
            "const cx=cv.getContext('2d');cx.fillStyle='#0a0a12';cx.fillRect(0,0,512,128);"
            "cx.fillStyle='%s';cx.font='bold 40px sans-serif';cx.textAlign='center';cx.textBaseline='middle';"
            "cx.fillText('%s',256,64);"
            "const tex=new THREE.CanvasTexture(cv);"
            "const m=new THREE.Mesh(new THREE.PlaneGeometry(4,1),"
            "new THREE.MeshBasicMaterial({map:tex,transparent:true}));"
            "scene.add(m);controls.target.set(0,0,0);"
            "animate=()=>{m.rotation.y=Math.sin(t.v*0.5)*0.3};"
        ) % (c0, safe)

    # default: knot
    return (
        "const knot=new THREE.Mesh(new THREE.TorusKnotGeometry(1.6,0.5,160,32),"
        "new THREE.MeshStandardMaterial({color:0x%06x,roughness:0.3,metalness:0.4}));"
        "scene.add(knot);controls.target.set(0,0,0);"
        "animate=()=>{knot.rotation.x+=0.005;knot.rotation.y+=0.008};"
    ) % i0


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#0a0a12;font-family:-apple-system,system-ui,sans-serif}
  #hud{position:fixed;left:12px;top:12px;color:#9fe;font-size:13px;line-height:1.5;background:rgba(0,0,0,.35);padding:8px 10px;border-radius:8px;max-width:70vw;pointer-events:none}
  #hud b{color:#fff} #hud .m{color:#fb6}
  #err{position:fixed;inset:0;display:none;align-items:center;justify-content:center;color:#f99;font-size:15px;text-align:center;padding:20px}
</style>
</head>
<body>
<div id="hud"><b>AOS 3D · 交互场景</b><br>提示词：__LABEL__<br><span class="m">模式：__MODE__ / 类型：__TYPE__</span><br>拖拽旋转 · 滚轮缩放</div>
<div id="err">无法加载 Three.js（需浏览器联网访问 CDN）。<br>请联网后重试，或部署本地 three.js 后修改本页引用。</div>
<script type="importmap">
{"imports":{"three":"__CDN__/build/three.module.js","three/addons/":"__CDN__/examples/jsm/"}}
</script>
<script type="module">
let scene, camera, renderer, controls, animate=()=>{};
try {
  const THREE = await import('three');
  const { OrbitControls } = await import('three/addons/controls/OrbitControls.js');
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a12);
  camera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, 0.1, 100);
  camera.position.set(0, 2, 7);
  renderer = new THREE.WebGLRenderer({antialias:true});
  renderer.setSize(innerWidth, innerHeight);
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  document.body.appendChild(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.autoRotate = true; controls.autoRotateSpeed = 1.2;
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 1.0); dir.position.set(5,8,6); scene.add(dir);
  const t = {v:0};
__SCENE_JS__
  addEventListener('resize', ()=>{ camera.aspect=innerWidth/innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });
  renderer.setAnimationLoop(()=>{ t.v+=0.016; animate(); controls.update(); renderer.render(scene,camera); });
} catch (e) {
  console.error(e); document.getElementById('err').style.display='flex';
}
</script>
</body>
</html>"""


def build_scene_html(prompt: str, mode: str) -> str:
    palette = _palette(prompt)
    st = _scene_type(prompt)
    title = _html.escape(prompt[:60] or "AOS 3D 场景")
    label = _html.escape(prompt[:80])
    return (
        _TEMPLATE
        .replace("__TITLE__", title)
        .replace("__LABEL__", label)
        .replace("__MODE__", mode)
        .replace("__TYPE__", st)
        .replace("__CDN__", THREE_CDN)
        .replace("__SCENE_JS__", _scene_js(st, palette, prompt))
    )


class ThreejsAdapter(BaseAgentAdapter):
    """从 prompt 生成可交互 3D 场景的适配器（MEDIA_3D）。

    当前用启发式「关键词→场景 + 调色板哈希」生成，零外部依赖、确定性。
    扩展点：invoke 里可先尝试用 LiteLLMAdapter 生成更丰富的 Three.js 场景 JS，
    失败时回退本生成器（保持「云端用不了就本地」）。
    """

    def __init__(self) -> None:
        logger.info("ThreejsAdapter: ready (browser-runtime 3D, zero server deps)")

    @property
    def engine_id(self) -> str:
        return "threejs"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.MEDIA_3D]

    def health(self) -> bool:
        return True  # 纯 Python 字符串生成，永远可用

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        prompt = (payload.get("prompt") or payload.get("task") or "").strip()
        if not prompt:
            return InvokeResult(ok=False, error="media.3d 需要 prompt")

        mode = "procedural"
        # 扩展点：此处可优先调用 LiteLLMAdapter 生成场景 JS；失败再走启发式。
        try:
            html = build_scene_html(prompt, mode)
        except Exception as e:  # noqa: BLE001
            return InvokeResult(ok=False, error=f"3D 场景生成失败: {e}")

        return InvokeResult(ok=True, data={
            "html": html,
            "mode": mode,
            "scene_type": _scene_type(prompt),
            "prompt": prompt,
            "engine": "threejs",
            "note": "交互发生在浏览器（拖拽旋转/滚轮缩放）；属自包含 HTML，无需服务端 GPU。",
        })
