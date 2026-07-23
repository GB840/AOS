# 自己搞 LLM 聚合（弃用 FreeLLMAPI，用 AOS 自有 LiteLLM 平面）

> 决策：FreeLLMAPI 的「卖点」是「免 key 聚合 16 家免费额度」，实测其公开端点
> `POST https://freellmapi.co/v1/chat/completions` 返回 **HTTP 405**（根域名是营销页，
> 不是 API）。真实架构下 16 家 key 还是**你自己填**。既然 key 自己填，FreeLLMAPI 就只是个
> 套壳转发器——AOS 自带的 **LiteLLM 推理平面**已经覆盖同等能力（100+ 供应商、OpenAI 兼容、
> 原生负载均衡 / fallback / 成本核算），而且 key 和数据都在你自己手里。所以**不用它，自己弄**。

---

## 方案 A：本机起 LiteLLM 代理（推荐，最贴近「自己弄」）

思路：你本机跑一个 LiteLLM 代理（:4000），把 16 家 key 全塞进它的配置；AOS 只认
`http://localhost:4000` 这一个 OpenAI 兼容端点。轮询 / 故障切换由 LiteLLM 原生完成。

### 1. 装 LiteLLM（已在 AOS 依赖里，可复用；也可单独装）
```powershell
pip install litellm
```

### 2. 写配置文件 `external/litellm-proxy/config.yaml`（自管，不进 git）
下面只列 3 家示例，照格式把 16 家补齐即可。每家填你自己的 key。
```yaml
model_list:
  # —— OpenAI ——
  - model_name: gpt-4o-mini
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY
  # —— DeepSeek（每月 1 亿免费 Token 档）——
  - model_name: deepseek-chat
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY
  # —— 智谱 GLM（国内稳）——
  - model_name: glm-4-flash
    litellm_params:
      model: zhipu/glm-4-flash
      api_key: os.environ/ZHIPU_API_KEY
  # 其余 13 家（Anthropic / Gemini / Qwen / Moonshot / SiliconFlow ...）照葫芦画瓢加
  # 每家一个 - model_name / litellm_params(model + api_key) 即可。

# 跨供应商容灾：某个挂了自动换下一个
router_settings:
  fallbacks:
    - gpt-4o-mini: ["deepseek-chat", "glm-4-flash"]
  num_retries: 2
```

### 3. 起代理
```powershell
$env:OPENAI_API_KEY="sk-你的"
$env:DEEPSEEK_API_KEY="sk-你的"
$env:ZHIPU_API_KEY="你的"
litellm --config external/litellm-proxy/config.yaml --port 4000
```
看到 `LiteLLM Proxy started on http://0.0.0.0:4000` 即就绪。

### 4. AOS 指向它（改 `D:\AOS\.env`）
```ini
LITELLM_API_BASE=http://localhost:4000
LITELLM_MODEL=gpt-4o-mini
# LITELLM_API_KEY_ENV 留空即可，代理侧已在管 key
```
重启 AOS（`start_all.sh` / `run.bat`）。AOS 的 `inference.llm` 能力会经 LiteLLM 适配器
打到 `localhost:4000`，由你的代理在 16 家之间轮询 / 容灾。

---

## 方案 B：不跑代理，直接在 AOS 注册多家（无额外进程）

适合只想用 2-3 家、不愿维护代理的情况。在 `fabric_hub.py` 注册多个 `LiteLLMAdapter`
实例，AOS 的 `registry.route()` 会做**跨供应商运行时故障转移**（已有语义）。

```python
# fabric_hub.py 默认注册处，照已有范式加：
for name, model, key_env in [
    ("openai",  "openai/gpt-4o-mini",  "OPENAI_API_KEY"),
    ("deepseek","deepseek/deepseek-chat","DEEPSEEK_API_KEY"),
    ("zhipu",   "zhipu/glm-4-flash",   "ZHIPU_API_KEY"),
]:
    try:
        from core.fabric.adapters.litellm_adapter import LiteLLMAdapter
        self._registry.register(
            LiteLLMAdapter(default_model=model),
            tier=TIER_MEDIUM,
        )
    except Exception as e:
        _LOG.warning("注册 %s 失败(跳过): %s", name, e)
```
`LITELLM_MODEL` / `LITELLM_API_KEY_ENV` 在 `.env` 里设默认那家即可。

---

## ⚠️ 商用红线（护眼眼镜项目务必遵守）
- 免费档 key 的 ToS 多为「评估 / 个人用途」，**量产商用走免费档大概率违规**。
- 用上面方案做**开发期多模型对比**完全没问题；**生产环境请用自己的合规 key**，
  或自托管合规层（你已经在做了——方案 A 就是你的合规层）。
- key 只在你本机 / 你自己的代理里，不进任何第三方（这正是弃用 FreeLLMAPI 的原因）。

## 验证（真实非虚拟）
```powershell
cd D:\AOS
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe -c "
from core.fabric.adapters.litellm_adapter import LiteLLMAdapter
a = LiteLLMAdapter()
print('health:', a.health())
r = a.invoke(type('R',(),{'payload':{'messages':[{'role':'user','content':'hi, 3 words'}]}})())
print('ok:', r.ok, '| content:', (r.data or {}).get('content'))
"
```
能看到真实模型回包即通。
