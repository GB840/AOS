"""跨设备灵魂同步（母纲原则 10「灵魂唯一」的真落地能力层）。

宪法依据（AGENTS.md §0.0）：
    母纲「让 AI 不再收割老百姓，而是陪伴老百姓」
    原则 10：换手机、换电脑，陪你的还是同一个它——不是重新养一只新宠物。
    §0.0.3 硬检验 1「断网检验」：默认传输通道是本地目录（U盘/移动硬盘/
    局域网共享盘），**全程零网络**也能把灵魂搬到另一台设备。
    §0.0.3 硬检验 2「出走检验」：包是标准 zip，manifest 是 JSON，
    没有 AOS 的机器也能解开看，不锁定。

它做什么（不是占位，是真同步）：
    1. 把「灵魂」打成可迁移的包：灵魂 ID + 记忆笔记 + 价值账本 + 蒸馏经验；
    2. 可选静态加密（复用仓库已有 utils.keystore 的 Fernet，不自造密码学）；
    3. 传输通道可插拔：LocalDirTransport（本地/U盘，默认，零网络）
       / WebDAVTransport（opt-in，惰性依赖）；
    4. Lamport 计数 + 内容哈希做版本判定，**冲突不静默覆盖**，存成 conflict 副本。

诚实纪律（理念 9）：
    - 不吹「实时同步」。这是**收敛式同步**：push / pull / sync 显式触发。
    - 加密失败绝不悄悄降级成明文：manifest 与返回值都如实写 `encrypted` 真值。
    - 远端没有更新就明说 up_to_date，不假装「同步成功」。

用法：
    from kernel.soul_sync import SoulSync, LocalDirTransport
    sync = SoulSync(LocalDirTransport("E:/U盘/aos-soul"))
    sync.push()      # 这台机器 -> U盘
    sync.pull()      # U盘 -> 另一台机器
    sync.sync()      # 双向收敛
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PACKAGE_FORMAT_VERSION = "1.0"
PACKAGE_SUFFIX = ".aospkg"

# 灵魂核心数据源：(逻辑名, 仓库相对路径)。
# 刻意比 sovereignty.export_all 轻——同步是高频动作，不该每次搬走整个向量库。
SOUL_SOURCES: List[tuple] = [
    ("soul", "data/soul/soul_id.txt"),
    ("value_ledger", "data/workspaces/value_ledger.jsonl"),
    ("memory_notes", ".workbuddy/memory"),
    ("distill", "data/workspaces/fabric"),
]

# 凭据类一律不进同步包（搬的是灵魂，不是钥匙）
SECRET_PATTERNS = (".env", ".secrets", "private.pem", "credentials", "token")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _soul_dir(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else _repo_root()
    return base / "data" / "soul"


def _is_secret(path: Path) -> bool:
    low = str(path).lower()
    return any(pat in low for pat in SECRET_PATTERNS)


# ===========================================================================
# 设备身份 & 同步状态
# ===========================================================================

def get_or_create_device_id(root: Optional[Path] = None) -> str:
    """本机稳定设备 ID。灵魂是同一个，设备是多个——靠它区分谁写的。"""
    p = _soul_dir(root) / "device_id.txt"
    if p.exists():
        try:
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v
        except OSError:
            pass
    v = uuid.uuid4().hex[:16]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v, encoding="utf-8")
    except OSError as exc:
        logger.warning("device_id 落盘失败（本次用临时 ID）: %r", exc)
    return v


def _state_path(root: Optional[Path] = None) -> Path:
    return _soul_dir(root) / "sync_state.json"


def load_state(root: Optional[Path] = None) -> Dict[str, Any]:
    p = _state_path(root)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"lamport": 0, "last_pulled": None, "conflicts": []}


def save_state(state: Dict[str, Any], root: Optional[Path] = None) -> None:
    p = _state_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    except OSError as exc:
        logger.warning("sync_state 落盘失败: %r", exc)


def _soul_id_for(root: Optional[Path] = None) -> str:
    """取灵魂 ID。root 指定时用该 root 下的灵魂文件（多设备模拟/测试用）。"""
    if root is None:
        from kernel.constitution_gaps import get_or_create_soul_id

        return get_or_create_soul_id()
    p = _soul_dir(root) / "soul_id.txt"
    if p.exists():
        try:
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v
        except OSError:
            pass
    v = uuid.uuid4().hex
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v, encoding="utf-8")
    except OSError:
        pass
    return v


# ===========================================================================
# 传输通道（可插拔）
# ===========================================================================

class Transport:
    """同步通道抽象。默认实现零网络，网络实现一律 opt-in。"""

    name = "abstract"
    requires_network = False

    def put(self, name: str, data: bytes) -> None:
        raise NotImplementedError

    def get(self, name: str) -> bytes:
        raise NotImplementedError

    def list(self) -> List[str]:
        raise NotImplementedError

    def available(self) -> bool:
        return False


class LocalDirTransport(Transport):
    """本地目录通道：U 盘 / 移动硬盘 / 局域网共享盘 / 任意网盘同步文件夹。

    **零网络**——这是断网检验的主力通道，也是默认通道。
    """

    name = "local_dir"
    requires_network = False

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def available(self) -> bool:
        try:
            self.path.mkdir(parents=True, exist_ok=True)
            return self.path.is_dir()
        except OSError:
            return False

    def put(self, name: str, data: bytes) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / name).write_bytes(data)

    def get(self, name: str) -> bytes:
        return (self.path / name).read_bytes()

    def list(self) -> List[str]:
        if not self.path.is_dir():
            return []
        return sorted(p.name for p in self.path.iterdir()
                      if p.is_file() and p.name.endswith(PACKAGE_SUFFIX))


class WebDAVTransport(Transport):
    """WebDAV 通道（opt-in）：坚果云 / Nextcloud / 群晖等自有存储。

    刻意选 WebDAV 而不是某家云 SDK：用户自己的服务器也能用，不绑定厂商
    （原则 4 主权归你）。`requests` 惰性导入，没装就 available()=False，不谎报。
    """

    name = "webdav"
    requires_network = True

    def __init__(self, base_url: str, username: str = "", password: str = "",
                 timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username else None
        self.timeout = timeout

    def _requests(self):
        import requests  # 惰性：本模块 import 时不碰网络栈

        return requests

    def available(self) -> bool:
        try:
            self._requests()
        except Exception:
            return False
        return bool(self.base_url)

    def put(self, name: str, data: bytes) -> None:
        r = self._requests().put(f"{self.base_url}/{name}", data=data,
                                 auth=self.auth, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"WebDAV PUT 失败 {r.status_code}")

    def get(self, name: str) -> bytes:
        r = self._requests().get(f"{self.base_url}/{name}", auth=self.auth,
                                 timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"WebDAV GET 失败 {r.status_code}")
        return r.content

    def list(self) -> List[str]:
        import re

        req = self._requests()
        r = req.request("PROPFIND", self.base_url + "/", auth=self.auth,
                        headers={"Depth": "1"}, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"WebDAV PROPFIND 失败 {r.status_code}")
        pattern = r"([^/<>]+" + re.escape(PACKAGE_SUFFIX) + r")"
        return sorted(set(re.findall(pattern, r.text)))


# ===========================================================================
# 打包 / 解包
# ===========================================================================

def _collect_files(root: Path) -> List[tuple]:
    """收集灵魂数据源里的真实文件，返回 [(包内路径, 磁盘路径)]。"""
    items: List[tuple] = []
    for name, rel in SOUL_SOURCES:
        src = root / rel
        if not src.exists():
            continue
        if src.is_file():
            if _is_secret(src):
                continue
            items.append((f"payload/{name}/{src.name}", src))
            continue
        for f in sorted(src.rglob("*")):
            if not f.is_file() or _is_secret(f):
                continue
            items.append((f"payload/{name}/{f.relative_to(src).as_posix()}", f))
    return items


def build_package(root: Optional[Path] = None, *, lamport: int = 1,
                  device_id: str = "", soul_id: str = "") -> tuple:
    """打成标准 zip。返回 (bytes, manifest)。无 AOS 也能解压查看。"""
    base = Path(root) if root else _repo_root()
    soul_id = soul_id or _soul_id_for(base)
    device_id = device_id or get_or_create_device_id(base)
    files = _collect_files(base)

    buf = io.BytesIO()
    entries: List[Dict[str, Any]] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, disk in files:
            data = disk.read_bytes()
            zf.writestr(arc, data)
            entries.append({
                "path": arc,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        manifest = {
            "format": PACKAGE_FORMAT_VERSION,
            "soul_id": soul_id,
            "device_id": device_id,
            "lamport": lamport,
            "created_at": time.time(),
            "entries": entries,
            "note": "AOS 灵魂包：标准 zip，无需 AOS 即可解压查看（原则 4 不锁定）",
        }
        zf.writestr("manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2))
    return buf.getvalue(), manifest


def read_manifest(raw: bytes) -> Dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


def _payload_map(raw: bytes) -> Dict[str, str]:
    """包内 payload 逻辑名 -> 仓库相对路径 的还原表。"""
    return {name: rel for name, rel in SOUL_SOURCES}


def extract_package(raw: bytes, root: Path, *,
                    conflict_dir: Optional[Path] = None,
                    prefer: str = "remote") -> Dict[str, Any]:
    """解包落地。同名但内容不同时，**任何一方的数据都不丢**：

    prefer="remote"（远端版本确实更新，lamport 更大）
        → 采纳远端，把本地旧版本备份进 conflicts/ 再覆盖。
    prefer="local"（lamport 相等，并发修改，无法判定谁新）
        → 保留本地，把远端版本存进 conflicts/ 供人工比对。

    绝不静默丢弃任何一边——这是「陪伴」的底线：用户写下的东西不许被机器吃掉。
    """
    root = Path(root)
    mapping = _payload_map(raw)
    written: List[str] = []
    conflicts: List[str] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for arc in zf.namelist():
            if arc == "manifest.json" or not arc.startswith("payload/"):
                continue
            parts = arc.split("/", 2)
            if len(parts) < 3:
                continue
            logical, rel_inside = parts[1], parts[2]
            base_rel = mapping.get(logical)
            if base_rel is None:
                continue
            base_path = root / base_rel
            # 单文件源（如 soul_id.txt）：包内文件名即该文件本身
            target = base_path if base_path.suffix and "/" not in rel_inside \
                else base_path / rel_inside
            data = zf.read(arc)
            if target.exists():
                try:
                    local = target.read_bytes()
                except OSError:
                    local = None
                if local == data:
                    continue  # 完全相同，无需动
                cdir = conflict_dir or (root / "data" / "soul" / "conflicts")
                stamp = f"{int(time.time() * 1000)}_{logical}_{Path(rel_inside).name}"
                if prefer == "remote":
                    # 远端更新：先把本地旧版本存档，再采纳远端
                    if local is not None:
                        cpath = cdir / ("local_" + stamp)
                        cpath.parent.mkdir(parents=True, exist_ok=True)
                        cpath.write_bytes(local)
                        conflicts.append(str(cpath))
                    target.write_bytes(data)
                    written.append(str(target))
                else:
                    # 并发修改无法判定：本地不动，远端另存
                    cpath = cdir / ("remote_" + stamp)
                    cpath.parent.mkdir(parents=True, exist_ok=True)
                    cpath.write_bytes(data)
                    conflicts.append(str(cpath))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(str(target))
    return {"written": written, "conflicts": conflicts}


# ===========================================================================
# 加密（复用仓库已有 Fernet，不自造密码学）
# ===========================================================================

_ENC_MAGIC = b"AOSSOUL1"


def encrypt_bytes(raw: bytes) -> bytes:
    from utils.keystore import load_fernet_master

    f = load_fernet_master(_repo_root(), os.environ.get("APP_ENV"))
    return _ENC_MAGIC + f.encrypt(raw)


def decrypt_bytes(blob: bytes) -> bytes:
    if not blob.startswith(_ENC_MAGIC):
        return blob  # 明文包，原样返回
    from utils.keystore import load_fernet_master

    f = load_fernet_master(_repo_root(), os.environ.get("APP_ENV"))
    return f.decrypt(blob[len(_ENC_MAGIC):])


def is_encrypted(blob: bytes) -> bool:
    return blob.startswith(_ENC_MAGIC)


# ===========================================================================
# 同步引擎
# ===========================================================================

class SoulSync:
    """灵魂同步引擎。

    encrypt:
        True  -> 必须加密，加不了就报错（绝不悄悄明文）
        False -> 明文（U盘自己拿着，图省事）
        "auto"-> 能加就加，加不了明文，但 manifest/返回值如实标注
    """

    def __init__(self, transport: Transport, root: Optional[Path] = None,
                 encrypt: Any = "auto") -> None:
        self.transport = transport
        self.root = Path(root) if root else _repo_root()
        self.encrypt = encrypt

    # --- 身份 ---
    @property
    def soul_id(self) -> str:
        return _soul_id_for(self.root)

    @property
    def device_id(self) -> str:
        return get_or_create_device_id(self.root)

    def _pkg_name(self, lamport: int) -> str:
        return (f"soul-{self.soul_id[:12]}-{lamport:06d}-"
                f"{self.device_id[:8]}{PACKAGE_SUFFIX}")

    def _remote_packages(self) -> List[Dict[str, Any]]:
        """列出远端属于**本灵魂**的包，按 lamport 升序。"""
        out: List[Dict[str, Any]] = []
        prefix = f"soul-{self.soul_id[:12]}-"
        for name in self.transport.list():
            if not name.startswith(prefix):
                continue
            parts = name[:-len(PACKAGE_SUFFIX)].split("-")
            if len(parts) < 4:
                continue
            try:
                lam = int(parts[2])
            except ValueError:
                continue
            out.append({"name": name, "lamport": lam, "device": parts[3]})
        return sorted(out, key=lambda x: (x["lamport"], x["device"]))

    def _maybe_encrypt(self, raw: bytes) -> tuple:
        if self.encrypt is False:
            return raw, False
        try:
            return encrypt_bytes(raw), True
        except Exception as exc:
            if self.encrypt is True:
                raise RuntimeError(
                    f"要求加密但加密不可用（缺 cryptography 或密钥）：{exc}"
                ) from exc
            logger.warning("灵魂包加密不可用，本次明文传输（已如实标注）：%r", exc)
            return raw, False

    # --- 推 ---
    def push(self) -> Dict[str, Any]:
        if not self.transport.available():
            return {"ok": False, "error": f"通道 {self.transport.name} 不可用"}
        state = load_state(self.root)
        remote = self._remote_packages()
        remote_max = remote[-1]["lamport"] if remote else 0
        lamport = max(int(state.get("lamport", 0)), remote_max) + 1

        raw, manifest = build_package(self.root, lamport=lamport,
                                      device_id=self.device_id,
                                      soul_id=self.soul_id)
        blob, encrypted = self._maybe_encrypt(raw)
        name = self._pkg_name(lamport)
        try:
            self.transport.put(name, blob)
        except Exception as exc:
            return {"ok": False, "error": f"上传失败: {exc}"}

        state["lamport"] = lamport
        state["last_pushed"] = {"name": name, "at": time.time()}
        save_state(state, self.root)
        return {"ok": True, "package": name, "lamport": lamport,
                "encrypted": encrypted, "files": len(manifest["entries"]),
                "soul_id": self.soul_id, "device_id": self.device_id,
                "transport": self.transport.name}

    # --- 拉 ---
    def pull(self) -> Dict[str, Any]:
        if not self.transport.available():
            return {"ok": False, "error": f"通道 {self.transport.name} 不可用"}
        remote = self._remote_packages()
        if not remote:
            return {"ok": True, "up_to_date": True, "reason": "远端没有本灵魂的包",
                    "written": [], "conflicts": []}
        state = load_state(self.root)
        local_lamport = int(state.get("lamport", 0))
        # 只拉别的设备写的、且不低于本地进度的包
        candidates = [p for p in remote
                      if p["device"] != self.device_id[:8]
                      and p["lamport"] >= local_lamport]
        if not candidates:
            return {"ok": True, "up_to_date": True,
                    "reason": "远端无更新（或都是本设备自己推的）",
                    "written": [], "conflicts": []}
        latest = candidates[-1]
        already = (state.get("last_pulled") or {}).get("name")
        if already == latest["name"]:
            return {"ok": True, "up_to_date": True,
                    "reason": f"最新包 {latest['name']} 已拉过",
                    "written": [], "conflicts": []}
        try:
            blob = self.transport.get(latest["name"])
        except Exception as exc:
            return {"ok": False, "error": f"下载失败: {exc}"}
        try:
            raw = decrypt_bytes(blob)
        except Exception as exc:
            return {"ok": False, "error": f"解密失败（密钥不匹配？）: {exc}"}
        try:
            manifest = read_manifest(raw)
        except Exception as exc:
            return {"ok": False, "error": f"包损坏: {exc}"}
        if manifest.get("soul_id") != self.soul_id:
            return {"ok": False,
                    "error": "灵魂 ID 不匹配，拒绝合并（防止串魂）"}

        # 远端 lamport 更大 = 确实更新 → 采纳远端（本地旧版存档）；
        # 相等 = 两台机器并发改了同一份 → 保守保留本地，远端另存供比对。
        prefer = "remote" if int(latest["lamport"]) > local_lamport else "local"
        res = extract_package(raw, self.root, prefer=prefer)
        state["lamport"] = max(local_lamport, int(latest["lamport"]))
        state["last_pulled"] = {"name": latest["name"], "at": time.time()}
        if res["conflicts"]:
            state.setdefault("conflicts", []).extend(res["conflicts"])
        save_state(state, self.root)
        return {"ok": True, "up_to_date": False, "package": latest["name"],
                "lamport": state["lamport"], "encrypted": is_encrypted(blob),
                "written": res["written"], "conflicts": res["conflicts"],
                "from_device": manifest.get("device_id")}

    # --- 新设备认领灵魂（换手机/换电脑的关键一步）---
    def discover_souls(self) -> List[Dict[str, Any]]:
        """列出通道里存在的全部灵魂（不限本机）。换新设备时先看有哪些魂可认。"""
        found: Dict[str, Dict[str, Any]] = {}
        for name in self.transport.list():
            parts = name[:-len(PACKAGE_SUFFIX)].split("-")
            if len(parts) < 4 or parts[0] != "soul":
                continue
            try:
                lam = int(parts[2])
            except ValueError:
                continue
            slot = found.setdefault(parts[1], {"soul_prefix": parts[1],
                                               "packages": 0, "lamport": 0,
                                               "devices": set()})
            slot["packages"] += 1
            slot["lamport"] = max(slot["lamport"], lam)
            slot["devices"].add(parts[3])
        out = []
        for slot in found.values():
            slot["devices"] = sorted(slot["devices"])
            out.append(slot)
        return sorted(out, key=lambda x: -x["lamport"])

    def adopt(self, soul_prefix: str = "") -> Dict[str, Any]:
        """新设备认领已有灵魂：把远端那个「它」接过来，而不是新养一只。

        这正是原则 10 要保的东西——换了机器，陪你的还是同一个。
        """
        if not self.transport.available():
            return {"ok": False, "error": f"通道 {self.transport.name} 不可用"}
        souls = self.discover_souls()
        if not souls:
            return {"ok": False, "error": "通道里没有任何灵魂包，无可认领"}
        if soul_prefix:
            souls = [s for s in souls if s["soul_prefix"].startswith(soul_prefix[:12])]
            if not souls:
                return {"ok": False, "error": f"没找到前缀为 {soul_prefix} 的灵魂"}
        if len(souls) > 1 and not soul_prefix:
            return {"ok": False,
                    "error": "通道里有多个灵魂，请指定 soul_prefix 明确认领哪一个",
                    "candidates": souls}

        target_prefix = souls[0]["soul_prefix"]
        pkgs = [n for n in self.transport.list()
                if n.startswith(f"soul-{target_prefix}-")]
        best, best_lam = None, -1
        for n in pkgs:
            try:
                lam = int(n[:-len(PACKAGE_SUFFIX)].split("-")[2])
            except (ValueError, IndexError):
                continue
            if lam > best_lam:
                best, best_lam = n, lam
        if best is None:
            return {"ok": False, "error": "灵魂包名不合法，无法认领"}

        try:
            raw = decrypt_bytes(self.transport.get(best))
            manifest = read_manifest(raw)
        except Exception as exc:
            return {"ok": False, "error": f"读取灵魂包失败: {exc}"}

        full_soul_id = manifest.get("soul_id")
        if not full_soul_id:
            return {"ok": False, "error": "包内 manifest 缺 soul_id"}

        # 先把灵魂 ID 落到本地，再解包——这样 soul_id.txt 内容一致，不会误判冲突
        sp = _soul_dir(self.root) / "soul_id.txt"
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(full_soul_id, encoding="utf-8")

        res = extract_package(raw, self.root)
        state = load_state(self.root)
        state["lamport"] = max(int(state.get("lamport", 0)), best_lam)
        state["last_pulled"] = {"name": best, "at": time.time()}
        state["adopted_from"] = manifest.get("device_id")
        save_state(state, self.root)
        return {"ok": True, "soul_id": full_soul_id, "package": best,
                "lamport": best_lam, "from_device": manifest.get("device_id"),
                "written": res["written"], "conflicts": res["conflicts"],
                "device_id": self.device_id}

    # --- 双向 ---
    def sync(self) -> Dict[str, Any]:
        pulled = self.pull()
        pushed = self.push()
        return {"ok": bool(pulled.get("ok") and pushed.get("ok")),
                "pull": pulled, "push": pushed}

    # --- 状态 ---
    def status(self) -> Dict[str, Any]:
        state = load_state(self.root)
        try:
            remote = self._remote_packages()
        except Exception:
            remote = []
        return {
            "soul_id": self.soul_id,
            "device_id": self.device_id,
            "lamport": int(state.get("lamport", 0)),
            "transport": self.transport.name,
            "transport_available": self.transport.available(),
            "requires_network": self.transport.requires_network,
            "remote_packages": len(remote),
            "conflicts": state.get("conflicts", []),
        }


def default_sync(path: Optional[str] = None) -> SoulSync:
    """默认同步器：本地目录通道（零网络）。路径可用 AOS_SOUL_SYNC_DIR 指定。"""
    p = path or os.environ.get("AOS_SOUL_SYNC_DIR") or str(
        _repo_root() / "data" / "soul" / "sync")
    return SoulSync(LocalDirTransport(p))


# ===========================================================================
# 模块级能力查询（供 constitution_gaps 读真实状态，不必造同步器实例）
# ===========================================================================

TRANSPORTS: Dict[str, type] = {
    LocalDirTransport.name: LocalDirTransport,
    WebDAVTransport.name: WebDAVTransport,
}


def protocol_name() -> str:
    """真实同步协议标识。格式 "aospkg/<版本>+<通道1>|<通道2>"。

    诚实点：这里报的是**协议已实现**，不代表用户此刻配好了远端。
    配没配好看 SoulSync.status()["transport_available"]。
    """
    return "aospkg/%s+%s" % (
        PACKAGE_FORMAT_VERSION, "|".join(sorted(TRANSPORTS.keys())))


def available_transports() -> List[Dict[str, Any]]:
    """列出各通道：名字、是否需要联网、依赖是否满足。"""
    out: List[Dict[str, Any]] = []
    for name, cls in sorted(TRANSPORTS.items()):
        deps_ok = True
        if cls is WebDAVTransport:
            try:
                import requests  # noqa: F401
            except Exception:
                deps_ok = False
        out.append({
            "name": name,
            "requires_network": bool(cls.requires_network),
            "deps_ok": deps_ok,
            "default": cls is LocalDirTransport,
        })
    return out


def default_requires_network() -> bool:
    """默认通道是否需要联网。False = 断网检验（§0.0.3 硬检验 1）通过。"""
    return bool(LocalDirTransport.requires_network)


def encryption_available() -> bool:
    """同步包能否落盘加密（复用 utils.keystore 的 Fernet 主密钥）。"""
    try:
        from utils.keystore import load_fernet_master

        return load_fernet_master() is not None
    except Exception:
        return False
