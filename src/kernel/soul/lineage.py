"""L3 数字家谱代际传承 + 死亡意识 —— 完全自研核心（生命体OS 白皮书 L3C/L3D）。

生命体六判据里最容易被跳过的两条：**能繁殖** 与（隐含的）**会死**。
一个不会死的系统不会珍惜资源，一个不能传承的系统每代都从零开始。

两块内容：

1. **数字家谱（Lineage）**：每个实例/粒子有出身（parent）、基因（继承的配置与教训）、
   生卒时间与后代。传承的**不是代码**，是「已验证有效的做法 + 已付出代价的教训」。
   继承有衰减：教训权重按代数打折，避免祖训僵化（对应 L4 双向思辨）。

2. **死亡意识（Mortality）**：实例知道自己有终点，并据此改变行为——
   - 剩余寿命 < 30% → 开始收尾（不接新长任务，优先把在手的做完）
   - 剩余寿命 < 10% → 强制遗嘱：把未沉淀的教训写进家谱再退出
   死亡不是崩溃：崩溃是丢信息，死亡是**有序移交**。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# 教训按代数衰减系数：第 n 代继承的祖训权重 = DECAY ** n
LESSON_DECAY = 0.7
# 低于此权重的祖训不再传下去（防止无限累积僵化）
LESSON_FLOOR = 0.2


@dataclass
class Lesson:
    """一条已付出代价的教训。"""

    text: str
    cost: float = 1.0            # 当初的代价（失败次数/耗时/花费）
    weight: float = 1.0          # 传承权重（随代数衰减）
    origin_gen: int = 0

    def inherited(self) -> Optional["Lesson"]:
        w = self.weight * LESSON_DECAY
        if w < LESSON_FLOOR:
            return None
        return Lesson(self.text, self.cost, round(w, 4), self.origin_gen)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Individual:
    """家谱中的一个个体（实例 / 粒子 / 一代 OS）。"""

    iid: str
    generation: int = 0
    parent: Optional[str] = None
    born_at: float = field(default_factory=time.time)
    died_at: Optional[float] = None
    lifespan_s: float = 3600.0            # 预期寿命
    genes: Dict[str, str] = field(default_factory=dict)     # 已验证有效的配置
    lessons: List[Lesson] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    epitaph: str = ""                     # 遗嘱/墓志铭：最后的移交说明

    # ---------------------------------------------------------- 死亡意识
    def age(self, now: Optional[float] = None) -> float:
        end = self.died_at or ((time.time() if now is None else now))
        return max(0.0, end - self.born_at)

    def remaining_ratio(self, now: Optional[float] = None) -> float:
        if self.lifespan_s <= 0:
            return 0.0
        return max(0.0, 1.0 - self.age(now) / self.lifespan_s)

    def alive(self, now: Optional[float] = None) -> bool:
        return self.died_at is None and self.remaining_ratio(now) > 0

    def mortality_stage(self, now: Optional[float] = None) -> str:
        """thriving / winding_down / last_will / dead —— 直接驱动调度行为。"""
        if not self.alive(now):
            return "dead"
        r = self.remaining_ratio(now)
        if r < 0.10:
            return "last_will"
        if r < 0.30:
            return "winding_down"
        return "thriving"

    def accepts_new_task(self, est_duration_s: float = 0.0,
                         now: Optional[float] = None) -> bool:
        """临终不接新活；收尾期只接能在剩余寿命内干完的活。"""
        stage = self.mortality_stage(now)
        if stage in ("dead", "last_will"):
            return False
        left = self.remaining_ratio(now) * self.lifespan_s
        if stage == "winding_down":
            return est_duration_s <= left * 0.8
        return est_duration_s <= left

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lessons"] = [l.to_dict() for l in self.lessons]
        return d


class Lineage:
    """数字家谱：出生、繁殖、传承、死亡、族谱查询。"""

    def __init__(self) -> None:
        self._people: Dict[str, Individual] = {}

    # ---------------------------------------------------------------- 出生
    def birth(self, iid: str, *, parent: Optional[str] = None,
              lifespan_s: float = 3600.0, genes: Optional[Dict[str, str]] = None,
              now: Optional[float] = None) -> Individual:
        if iid in self._people:
            raise ValueError(f"个体 {iid} 已存在于家谱")
        gen = 0
        inherited_genes: Dict[str, str] = {}
        inherited_lessons: List[Lesson] = []
        if parent is not None:
            p = self._people.get(parent)
            if p is None:
                raise ValueError(f"父代 {parent} 不在家谱中")
            gen = p.generation + 1
            inherited_genes = dict(p.genes)
            for l in p.lessons:
                nl = l.inherited()
                if nl is not None:
                    inherited_lessons.append(nl)
            p.children.append(iid)
        inherited_genes.update(genes or {})
        ind = Individual(iid=iid, generation=gen, parent=parent,
                         born_at=(time.time() if now is None else now), lifespan_s=lifespan_s,
                         genes=inherited_genes, lessons=inherited_lessons)
        self._people[iid] = ind
        return ind

    # ---------------------------------------------------------------- 传承
    def learn(self, iid: str, text: str, cost: float = 1.0) -> Lesson:
        """记下一条教训（只记真实付出过代价的，不记空话）。"""
        ind = self._require(iid)
        l = Lesson(text=text.strip(), cost=cost, weight=1.0, origin_gen=ind.generation)
        ind.lessons.append(l)
        return l

    def encode_gene(self, iid: str, key: str, value: str) -> None:
        """把一条**已验证有效**的做法写进基因，供后代默认继承。"""
        self._require(iid).genes[key] = value

    def inheritance_of(self, iid: str) -> Dict[str, object]:
        """这个个体将传给后代的东西（预览，不产生副作用）。"""
        ind = self._require(iid)
        kept = [l.inherited() for l in ind.lessons]
        return {"genes": dict(ind.genes),
                "lessons": [l.to_dict() for l in kept if l is not None],
                "dropped": sum(1 for l in kept if l is None)}

    # ---------------------------------------------------------------- 死亡
    def die(self, iid: str, epitaph: str = "", now: Optional[float] = None) -> Individual:
        """有序死亡：写遗嘱 → 标记卒年。教训已在家谱中，不随个体消失。"""
        ind = self._require(iid)
        ind.died_at = (time.time() if now is None else now)
        ind.epitaph = epitaph or f"{iid} 于第 {ind.generation} 代终，留下 {len(ind.lessons)} 条教训"
        return ind

    def reap(self, now: Optional[float] = None) -> List[str]:
        """回收寿命到期但未标记死亡的个体（防僵尸实例）。"""
        now = (time.time() if now is None else now)
        dead = [i for i, p in self._people.items()
                if p.died_at is None and p.remaining_ratio(now) <= 0]
        for i in dead:
            self.die(i, now=now)
        return dead

    # ---------------------------------------------------------------- 查询
    def get(self, iid: str) -> Optional[Individual]:
        return self._people.get(iid)

    def ancestors(self, iid: str) -> List[str]:
        out, cur = [], self._require(iid).parent
        while cur:
            out.append(cur)
            cur = self._people[cur].parent if cur in self._people else None
        return out

    def descendants(self, iid: str) -> List[str]:
        out: List[str] = []
        stack = list(self._require(iid).children)
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(self._people[c].children)
        return out

    def living(self, now: Optional[float] = None) -> List[Individual]:
        return [p for p in self._people.values() if p.alive(now)]

    def generations(self) -> int:
        return (max((p.generation for p in self._people.values()), default=-1) + 1)

    def _require(self, iid: str) -> Individual:
        p = self._people.get(iid)
        if p is None:
            raise KeyError(f"个体 {iid} 不在家谱中")
        return p

    # ---------------------------------------------------------------- 持久化
    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([i.to_dict() for i in self._people.values()],
                                ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def load(self, path: str | Path) -> int:
        p = Path(path)
        if not p.exists():
            return 0
        for d in json.loads(p.read_text(encoding="utf-8")):
            lessons = [Lesson(**l) for l in d.pop("lessons", [])]
            ind = Individual(**d)
            ind.lessons = lessons
            self._people[ind.iid] = ind
        return len(self._people)

    def __len__(self) -> int:
        return len(self._people)


__all__ = ["Lineage", "Individual", "Lesson", "LESSON_DECAY", "LESSON_FLOOR"]
