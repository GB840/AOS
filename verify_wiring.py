import re, json, sys, time
import urllib.request, urllib.error

env = open('.env', encoding='utf-8').read()
API_KEY = re.search(r'^API_KEY\s*=\s*(\S+)', env, re.M).group(1).strip()
BASE = "http://127.0.0.1:8000"
H = {"Content-Type": "application/json", "X-API-Key": API_KEY}

def req(method, path, body=None, token=None):
    hd = dict(H)
    if token:
        hd["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=hd, method=method)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, str(e)

out = []
def log(*a):
    s = " ".join(str(x) for x in a)
    out.append(s); print(s, flush=True)

# 1) health
st = req("GET", "/health")[0]
log("=== /health:", st)

# 2) fabric live engines
st, data = req("GET", "/api/fabric")
log("=== /api/fabric status:", st, "| live:", data.get("live"))
for e in data.get("engines", []):
    log(f"   - {e['engine_id']:12} live={e.get('live')} caps={e.get('capabilities')}")

# 3) OAuth2 token
st, data = req("POST", "/api/auth/token", {"username": "admin", "password": "admin"})
tok = data.get("access_token")
log("=== /api/auth/token:", st, "| token_type:", data.get("token_type"), "| len:", len(tok) if tok else 0)

# 4) Bearer works
st, data = req("GET", "/api/fabric", token=tok)
log("=== Bearer /api/fabric:", st, "| live:", data.get("live"))

# 5) wrong token -> 401
st, _ = req("GET", "/api/fabric", token="eyJhbGciOiJIUzI1NiJ9.invalid")
log("=== wrong Bearer -> expect 401:", st)

# 6) semantic search
st, data = req("POST", "/api/search", {"query": "机器学习属于什么学科", "search_type": "semantic"})
res = data.get("results", [])
log("=== /api/search semantic:", st, "| results:", len(res))
for r in res[:3]:
    log("   -", str(r.get("content", ""))[:42])

with open("verify_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
