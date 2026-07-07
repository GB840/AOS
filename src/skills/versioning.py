from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import json
import hashlib
import logging

logger = logging.getLogger(__name__)

class Version:
    def __init__(self, version_str: str):
        self.major, self.minor, self.patch = self._parse_version(version_str)
    
    def _parse_version(self, version_str: str) -> tuple:
        parts = version_str.split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __lt__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __eq__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def bump_major(self) -> "Version":
        return Version(f"{self.major + 1}.0.0")
    
    def bump_minor(self) -> "Version":
        return Version(f"{self.major}.{self.minor + 1}.0")
    
    def bump_patch(self) -> "Version":
        return Version(f"{self.major}.{self.minor}.{self.patch + 1}")

class VersionHistory:
    def __init__(self):
        self.versions: Dict[str, Dict] = {}
    
    def add_version(self, version: str, changes: List[str], author: str = "system", timestamp: Optional[datetime] = None):
        self.versions[version] = {
            "version": version,
            "changes": changes,
            "author": author,
            "timestamp": timestamp or datetime.now().isoformat(),
        }
    
    def get_version(self, version: str) -> Optional[Dict]:
        return self.versions.get(version)
    
    def get_latest(self) -> Optional[str]:
        if not self.versions:
            return None
        versions = sorted([Version(v) for v in self.versions.keys()])
        return str(versions[-1])
    
    def get_all_versions(self) -> List[str]:
        return sorted([str(Version(v)) for v in self.versions.keys()])
    
    def get_changelog(self) -> str:
        lines = []
        versions = sorted([Version(v) for v in self.versions.keys()], reverse=True)
        
        for v in versions:
            info = self.versions[str(v)]
            lines.append(f"## {v}")
            lines.append(f"**作者**: {info['author']}")
            lines.append(f"**时间**: {info['timestamp']}")
            lines.append("**变更**:")
            for change in info["changes"]:
                lines.append(f"- {change}")
            lines.append("")
        
        return "\n".join(lines)

class SkillVersionManager:
    def __init__(self, storage_path: str = "outputs/skills/versions"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._load_history()
    
    def _load_history(self):
        self.history: Dict[str, VersionHistory] = {}
        
        for filepath in self.storage_path.glob("*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                skill_name = filepath.stem
                self.history[skill_name] = VersionHistory()
                for version, info in data.items():
                    self.history[skill_name].add_version(
                        version,
                        info["changes"],
                        info["author"],
                        info["timestamp"],
                    )
            except Exception as e:
                logger.warning(f"Failed to load history for {filepath}: {e}")
    
    def _save_history(self, skill_name: str):
        filepath = self.storage_path / f"{skill_name}.json"
        
        history = self.history.get(skill_name)
        if history:
            data = history.versions
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    def create_version(self, skill_name: str, changes: List[str], author: str = "system", bump_type: str = "patch") -> str:
        if skill_name not in self.history:
            self.history[skill_name] = VersionHistory()
        
        history = self.history[skill_name]
        latest = history.get_latest()
        
        if latest:
            current_version = Version(latest)
            if bump_type == "major":
                new_version = current_version.bump_major()
            elif bump_type == "minor":
                new_version = current_version.bump_minor()
            else:
                new_version = current_version.bump_patch()
        else:
            new_version = Version("1.0.0")
        
        history.add_version(str(new_version), changes, author)
        self._save_history(skill_name)
        
        logger.info(f"Created version {new_version} for skill {skill_name}")
        return str(new_version)
    
    def get_history(self, skill_name: str) -> Optional[VersionHistory]:
        return self.history.get(skill_name)
    
    def get_latest_version(self, skill_name: str) -> Optional[str]:
        history = self.history.get(skill_name)
        if history:
            return history.get_latest()
        return None
    
    def get_all_versions(self, skill_name: str) -> List[str]:
        history = self.history.get(skill_name)
        if history:
            return history.get_all_versions()
        return []
    
    def get_changelog(self, skill_name: str) -> str:
        history = self.history.get(skill_name)
        if history:
            return history.get_changelog()
        return "暂无版本历史"
    
    def compare_versions(self, skill_name: str, version1: str, version2: str) -> Dict[str, Any]:
        history = self.history.get(skill_name)
        if not history:
            return {"error": "Skill not found"}
        
        v1_info = history.get_version(version1)
        v2_info = history.get_version(version2)
        
        if not v1_info or not v2_info:
            return {"error": "Version not found"}
        
        return {
            "version1": version1,
            "version2": version2,
            "v1_changes": v1_info["changes"],
            "v2_changes": v2_info["changes"],
            "v1_timestamp": v1_info["timestamp"],
            "v2_timestamp": v2_info["timestamp"],
            "v1_author": v1_info["author"],
            "v2_author": v2_info["author"],
        }
    
    def revert_to_version(self, skill_name: str, version: str) -> bool:
        history = self.history.get(skill_name)
        if not history or not history.get_version(version):
            return False
        
        logger.info(f"Reverted skill {skill_name} to version {version}")
        return True
    
    def list_all_skills(self) -> List[str]:
        return list(self.history.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        stats = {
            "total_skills": len(self.history),
            "total_versions": sum(len(h.versions) for h in self.history.values()),
            "skills": {},
        }
        
        for skill_name, history in self.history.items():
            stats["skills"][skill_name] = {
                "versions": len(history.versions),
                "latest": history.get_latest(),
            }
        
        return stats

class SkillSnapshot:
    def __init__(self, skill_name: str, version: str, content: Dict[str, Any], timestamp: Optional[datetime] = None):
        self.skill_name = skill_name
        self.version = version
        self.content = content
        self.timestamp = timestamp or datetime.now().isoformat()
        self.hash = self._compute_hash(content)
    
    def _compute_hash(self, content: Dict[str, Any]) -> str:
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "version": self.version,
            "content": self.content,
            "timestamp": self.timestamp,
            "hash": self.hash,
        }

class SnapshotManager:
    def __init__(self, storage_path: str = "outputs/skills/snapshots"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def save_snapshot(self, snapshot: SkillSnapshot):
        filepath = self.storage_path / f"{snapshot.skill_name}_{snapshot.version}_{snapshot.hash[:8]}.json"
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved snapshot for {snapshot.skill_name} v{snapshot.version}")
    
    def load_snapshot(self, skill_name: str, version: str) -> Optional[SkillSnapshot]:
        for filepath in self.storage_path.glob(f"{skill_name}_{version}_*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SkillSnapshot(
                    data["skill_name"],
                    data["version"],
                    data["content"],
                    data["timestamp"],
                )
            except Exception as e:
                logger.warning(f"Failed to load snapshot {filepath}: {e}")
        
        return None
    
    def list_snapshots(self, skill_name: Optional[str] = None) -> List[Dict[str, Any]]:
        snapshots = []
        
        for filepath in self.storage_path.glob("*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if skill_name and data["skill_name"] != skill_name:
                    continue
                
                snapshots.append(data)
            except Exception as e:
                logger.warning(f"Failed to read snapshot {filepath}: {e}")
        
        return sorted(snapshots, key=lambda x: x["timestamp"], reverse=True)

_default_version_manager = None
_default_snapshot_manager = None

def get_version_manager() -> SkillVersionManager:
    global _default_version_manager
    if _default_version_manager is None:
        _default_version_manager = SkillVersionManager()
    return _default_version_manager

def get_snapshot_manager() -> SnapshotManager:
    global _default_snapshot_manager
    if _default_snapshot_manager is None:
        _default_snapshot_manager = SnapshotManager()
    return _default_snapshot_manager