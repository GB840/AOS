"""L3 年轮时空记忆 + 数字家谱 + 死亡意识单测（白皮书 L3A/L3B/L3C/L3D）。"""
import pytest

from kernel.soul import TreeRingMemory, Lineage
from kernel.soul.tree_ring import DAY, RING_FRESH, RING_RECENT, RING_SEASON, RING_CORE
from kernel.soul.lineage import LESSON_DECAY, LESSON_FLOOR


# ------------------------------------------------------------ 年轮记忆
def test_fresh_memory_keeps_full_text():
    m = TreeRingMemory()
    long_text = "单创OS 定价讨论：" + "细节" * 200
    m.remember(long_text, locus="pricing")
    m.grow_rings(now=0)   # 刚写入，年龄为负→仍在 fresh
    assert len(m.recall(locus="pricing")[0].text) == len(long_text)


def test_rings_compress_with_age():
    now = 1_000_000.0
    m = TreeRingMemory()
    m.remember("A" * 2000, locus="p", when=now - 0.5 * DAY)     # fresh
    m.remember("B" * 2000, locus="p", when=now - 3 * DAY)       # recent
    m.remember("C" * 2000, locus="p", when=now - 30 * DAY)      # season
    m.remember("D" * 2000, locus="p", when=now - 400 * DAY)     # core
    census = m.grow_rings(now=now)
    assert census == {"fresh": 1, "recent": 1, "season": 1, "core": 1}
    lens = sorted(len(x.text) for x in m.recall(locus="p", limit=10))
    assert lens[0] < lens[1] < lens[2] < lens[3]     # 越内圈越短
    # fresh 圈按设计无损（近事记得清），压缩率下限被它托住，
    # 所以整体只验「确实压过」，压得狠不狠看内三圈。
    assert 0.2 < m.compression_ratio() < 0.4
    by_ring = {x.ring: x for x in m.recall(locus="p", limit=10)}
    assert len(by_ring[RING_FRESH].text) == 2000                    # 无损
    inner = sum(len(by_ring[r].text) for r in (RING_RECENT, RING_SEASON, RING_CORE))
    assert inner / 6000 < 0.12                                      # 内三圈压到 12% 以下


def test_hot_memory_ages_slower():
    """常被想起的事记得更细（热度延缓晋升一圈）。"""
    now = 1_000_000.0
    m = TreeRingMemory()
    hot = m.remember("H" * 1000, locus="p", when=now - 30 * DAY)
    cold = m.remember("C" * 1000, locus="p", when=now - 30 * DAY)
    hot.hits = 6
    m.grow_rings(now=now)
    assert hot.ring == RING_RECENT and cold.ring == RING_SEASON
    assert len(hot.text) > len(cold.text)


def test_spatiotemporal_slice_recall():
    now = 1_000_000.0
    m = TreeRingMemory()
    m.remember("定价踩坑：低估了支付通道费", locus="pricing", when=now - 5 * DAY,
               tags=["坑", "钱"])
    m.remember("护眼眼镜光学方案对比", locus="glasses", when=now - 5 * DAY)
    m.remember("很久以前的定价笔记", locus="pricing", when=now - 300 * DAY)
    hits = m.recall(locus="pricing", since=now - 10 * DAY)
    assert len(hits) == 1 and "支付通道费" in hits[0].text
    assert m.recall(tags=["坑"])[0].locus == "pricing"
    assert m.loci() == ["glasses", "pricing"]


def test_recall_increases_hits_and_timeline():
    m = TreeRingMemory()
    m.remember("事件一", locus="x", when=100)
    m.remember("事件二", locus="x", when=200)
    got = m.recall(locus="x")
    assert got[0].text == "事件二"          # 新的优先
    assert all(g.hits == 1 for g in got)
    tl = m.timeline("x")
    assert [t[0] for t in tl] == [100, 200]


def test_save_load_roundtrip(tmp_path):
    m = TreeRingMemory()
    m.remember("记忆一", locus="a", tags=["t"])
    p = m.save(tmp_path / "mem.json")
    m2 = TreeRingMemory()
    assert m2.load(p) == 1
    assert m2.recall("记忆一")[0].locus == "a"


def test_forget():
    m = TreeRingMemory()
    mm = m.remember("要忘的", locus="a")
    assert m.forget(mm.mid) is True and len(m) == 0
    assert m.forget("nope") is False


# ------------------------------------------------------------ 数字家谱
def test_birth_inherits_genes_and_lessons():
    lg = Lineage()
    lg.birth("gen0", lifespan_s=1000, now=0)
    lg.encode_gene("gen0", "search_engine", "anysearch_first")
    lg.learn("gen0", "别在无网环境重试三次", cost=3.0)
    child = lg.birth("gen1", parent="gen0", now=0)
    assert child.generation == 1
    assert child.genes["search_engine"] == "anysearch_first"
    assert len(child.lessons) == 1
    assert abs(child.lessons[0].weight - LESSON_DECAY) < 1e-9


def test_lesson_decays_and_drops_after_generations():
    """祖训按代衰减，低于地板不再传——防止祖训僵化。"""
    lg = Lineage()
    lg.birth("g0", now=0)
    lg.learn("g0", "一条祖训")
    prev = "g0"
    for i in range(1, 6):
        prev = lg.birth(f"g{i}", parent=prev, now=0).iid
    last = lg.get("g5")
    assert last.generation == 5
    assert all(l.weight >= LESSON_FLOOR for l in last.lessons)
    # 第 5 代应已丢弃（0.7^5 = 0.168 < 0.2）
    assert len(last.lessons) == 0


def test_inheritance_preview_reports_dropped():
    lg = Lineage()
    lg.birth("g0", now=0)
    l = lg.learn("g0", "弱教训")
    l.weight = 0.25          # 再衰减一次就低于地板
    info = lg.inheritance_of("g0")
    assert info["dropped"] == 1 and info["lessons"] == []


def test_mortality_stages_drive_task_acceptance():
    lg = Lineage()
    ind = lg.birth("x", lifespan_s=100, now=0)
    assert ind.mortality_stage(now=0) == "thriving"
    assert ind.accepts_new_task(50, now=0) is True
    assert ind.mortality_stage(now=75) == "winding_down"
    assert ind.accepts_new_task(30, now=75) is False      # 剩 25，超 80% 阈值
    assert ind.accepts_new_task(15, now=75) is True
    assert ind.mortality_stage(now=95) == "last_will"
    assert ind.accepts_new_task(1, now=95) is False       # 临终不接新活


def test_die_writes_epitaph_and_keeps_lessons():
    lg = Lineage()
    lg.birth("x", lifespan_s=100, now=0)
    lg.learn("x", "教训会留下")
    lg.die("x", now=50)
    assert lg.get("x").alive(now=60) is False
    assert "教训" in lg.get("x").lessons[0].text
    assert lg.get("x").epitaph


def test_reap_kills_zombies():
    lg = Lineage()
    lg.birth("z", lifespan_s=10, now=0)
    assert lg.reap(now=100) == ["z"]
    assert lg.living(now=100) == []


def test_ancestors_and_descendants():
    lg = Lineage()
    lg.birth("a", now=0)
    lg.birth("b", parent="a", now=0)
    lg.birth("c", parent="b", now=0)
    assert lg.ancestors("c") == ["b", "a"]
    assert sorted(lg.descendants("a")) == ["b", "c"]
    assert lg.generations() == 3


def test_unknown_parent_rejected():
    lg = Lineage()
    with pytest.raises(ValueError):
        lg.birth("x", parent="ghost")


def test_lineage_save_load(tmp_path):
    lg = Lineage()
    lg.birth("a", now=0)
    lg.learn("a", "教训")
    p = lg.save(tmp_path / "lineage.json")
    lg2 = Lineage()
    assert lg2.load(p) == 1
    assert lg2.get("a").lessons[0].text == "教训"
