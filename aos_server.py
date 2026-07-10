#!/usr/bin/env python3
"""AOS v1.0 — 综合版。内核路由 + LLM语义降级 + 学习缓存。"""

import sys, os, json, time
sys.path.insert(0, "src")
for f in ["API_KEY_HASH","ADMIN_USERNAME","ADMIN_PASSWORD","POSTGRES_PASSWORD","AOS_TOKEN_SECRET"]:
    os.environ.setdefault(f, "aos")
_E = os.path.join(os.path.dirname(__file__) if "__file__" in dir() else ".", ".env")
if os.path.exists(_E):
    with open(_E, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from kernel.system import build_default_system
from kernel.types import AgentSpec, Message
from kernel.router import get_router, register_builtins

sys = build_default_system()
k = sys.kernel
k.register_agent(AgentSpec("assistant", "Assistant", "litellm", ["chat"]))

router = get_router()
register_builtins(router)

# LLM 语义路由降级（关键词没命中时尝试）
def llm_route(text, caps):
    try:
        r = k.send_message(Message(sender="router", recipient="assistant",
            payload={"prompt": f"你是一个路由器。用户说: \"{text}\"。可用能力: {caps}。只返回最匹配的能力名，不要解释。都不匹配返回 none。"}))
        if r.ok and r.data:
            raw = r.data.get("content","").strip().lower()
            for c in caps:
                if c in raw: return c
    except: pass
    return None
router.set_llm_router(llm_route)

HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AOS v1.0</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#0f0f14;color:#e0e0e0;height:100vh;display:flex}
.sidebar{width:180px;background:#16161f;padding:12px}.sidebar h2{font-size:14px;font-weight:500;color:#7f77dd;margin-bottom:8px}
.sidebar .cap{cursor:pointer;padding:6px 10px;border-radius:6px;font-size:11px;color:#888;margin-bottom:2px}.sidebar .cap:hover{background:#222;color:#ccc}
.main{flex:1;display:flex;flex-direction:column}.header{background:#16161f;padding:8px 16px;font-size:11px;color:#555;border-bottom:1px solid #222}
.chat-area{flex:1;overflow-y:auto;padding:14px 18px}.msg{margin-bottom:10px;display:flex;gap:8px}.msg.user{flex-direction:row-reverse}
.msg .bubble{padding:10px 14px;border-radius:10px;max-width:82%;font-size:13px;line-height:1.5;white-space:pre-wrap}
.msg.user .bubble{background:#378ADD;color:#fff}.msg.skill .bubble{background:#1a2a1a;color:#5dcaa5;font-size:12px}
.msg.ai .bubble{background:#222235;color:#ccc}.msg .meta{font-size:10px;color:#555;margin-top:2px}
.input-bar{background:#16161f;padding:10px 16px;display:flex;gap:8px;border-top:1px solid #222}
.input-bar input{flex:1;padding:10px 14px;border-radius:8px;border:1px solid #333;background:#0f0f14;color:#ccc;font-size:13px}
.input-bar button{padding:10px 16px;border-radius:8px;border:none;background:#7f77dd;color:#fff;font-size:13px;font-weight:500;cursor:pointer}
.badge{display:inline-block;font-size:10px;padding:1px 5px;border-radius:3px;margin-right:5px}.bg-s{background:#1d9e75;color:#fff}.bg-a{background:#7f77dd;color:#fff}.bg-l{background:#ba7517;color:#fff}
</style></head><body><div class="sidebar"><h2>AOS v1.0</h2></div>
<div class="main"><div class="header">AOS v1.0 — 关键词+LLM语义路由 · 学习缓存</div><div class="chat-area" id="chat"></div>
<div class="input-bar"><input id="inp" placeholder="随便说... 搜索/计算/代码/时间/系统 自动识别" onkeydown="if(event.key==='Enter')send()"><button onclick="send()">发送</button></div></div>
<script>
fetch('/api/caps').then(r=>r.json()).then(d=>{var s=document.querySelector('.sidebar');d.forEach(c=>{var e=document.createElement('div');e.className='cap';e.onclick=()=>q(c.description);e.innerHTML=(c.icon||'')+' '+c.description+(c.needs_install?' <span style=font-size:9px;color:orange>需安装</span>':'');s.appendChild(e)})})
function q(t){document.getElementById('inp').value=t;send()}
function send(){
 var inp=document.getElementById('inp'),text=inp.value.trim();if(!text)return;inp.value='';
 var d=document.getElementById('chat'),u=document.createElement('div');u.className='msg user';u.innerHTML='<div class="bubble">'+text.replace(/</g,'&lt;')+'</div>';d.appendChild(u);
 fetch('/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:text})}).then(r=>r.json()).then(r=>{
  var cls=r.skill?'skill':'ai',badge=r.skill?(r.llm_route?'<span class="badge bg-l">LLM</span>':'<span class="badge bg-s">技能</span>'):'<span class="badge bg-a">AI</span>';
  var m=document.createElement('div');m.className='msg '+cls;m.innerHTML='<div class="bubble">'+badge+r.text.replace(/</g,'&lt;')+'</div><div class="meta">'+r.meta+'</div>';
  d.appendChild(m);d.scrollTop=d.scrollHeight
 })
}
</script></body></html>"""

from http.server import HTTPServer, BaseHTTPRequestHandler
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/caps": self._json(router.list_capabilities())
        else: self._html(HTML)
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        prompt = body.get("prompt", "")
        cap = router.route(prompt)
        llm_routed = cap and cap not in [c for c in ["search","calc","code","time","status"] if any(kw.lower() in prompt.lower() for kw in router._caps.get(c, type('',(),{'keywords':[]})()).keywords)]
        if cap:
            result = router.execute(cap, prompt)
            if result: self._json({"text": result, "skill": cap, "llm_route": llm_routed, "meta": f"{'LLM路由' if llm_routed else '关键词路由'} · {time.strftime('%H:%M:%S')}"}); return
            # 执行返回None → 能力存在但无法处理 → 回退LLM
        t0 = time.monotonic()
        r = k.send_message(Message(sender="web", recipient="assistant", payload={"prompt": prompt}))
        lat = round(time.monotonic() - t0, 2)
        text = r.data.get("content", "")[:1500] if r.data else r.error
        self._json({"text": text, "llm": True, "meta": f"Zhipu · {lat}s"})
    def _html(self, c): self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(c.encode())
    def _json(self, d): self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(d, ensure_ascii=False).encode())
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"AOS v1.0 — http://localhost:8000 ({router.count} caps, LLM fallback)")
    HTTPServer(("0.0.0.0", 8000), H).serve_forever()
