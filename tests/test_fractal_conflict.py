"""L2G 粒子冲突协调协议 + L7 四类粒子接口单测（白皮书 L2G / L7）。"""
import pytest

from kernel.fractal import (
    ConflictCoordinator, ConflictEscalation,
    ParticleRegistry, SENSOR, WORKER, GUARDIAN, ARCHIVIST,
)
from kernel.fractal.particles import (
    CAP_WRITE, CAP_VETO, CAP_SPAWN, CAP_MEMORY_WRITE, CAP_NET,
)


# ------------------------------------------------------- 冲突协调
def test_free_resource_granted():
    c = ConflictCoordinator()
    r = c.acquire("file:/tmp/a", "p1")
    assert r.granted and c.holder_of("file:/tmp/a") == "p1"


def test_parent_generation_preempts_child():
    """父代永远优先，防子体饿死父体。"""
    c = ConflictCoordinator()
    c.acquire("port:8080", "child", generation=2, priority=99)
    r = c.acquire("port:8080", "parent", generation=0, priority=0)
    assert r.granted is True and r.preempted == "child"


def test_same_generation_higher_priority_wins():
    c = ConflictCoordinator()
    c.acquire("db", "low", generation=1, priority=1)
    r = c.acquire("db", "high", generation=1, priority=5)
    assert r.granted and r.preempted == "low"


def test_loser_yields_without_silent_overwrite():
    c = ConflictCoordinator()
    c.acquire("db", "high", generation=1, priority=5)
    r = c.acquire("db", "low", generation=1, priority=1)
    assert r.granted is False and "让位" in r.reason
    assert c.holder_of("db") == "high"


def test_repeated_failure_escalates():
    c = ConflictCoordinator(max_preempt_fails=3)
    c.acquire("db", "high", generation=0, priority=9)
    c.acquire("db", "low", generation=1)
    c.acquire("db", "low", generation=1)
    with pytest.raises(ConflictEscalation):
        c.acquire("db", "low", generation=1)


def test_expired_lease_is_reaped_no_deadlock():
    """持有者崩溃也不能永久占住资源。"""
    c = ConflictCoordinator()
    c.acquire("gpu", "crashed", ttl=10.0, now=1000.0)
    r = c.acquire("gpu", "newcomer", generation=5, now=1011.0)
    assert r.granted and "空闲" in r.reason


def test_renew_and_release():
    c = ConflictCoordinator()
    c.acquire("gpu", "p1")
    assert c.acquire("gpu", "p1").reason == "续租成功"
    assert c.release("gpu", "p2") is False       # 非持有者不能释放
    assert c.release("gpu", "p1") is True
    assert c.holder_of("gpu") is None


def test_release_all_on_particle_death():
    c = ConflictCoordinator()
    c.acquire("a", "p1"); c.acquire("b", "p1"); c.acquire("c", "p2")
    assert c.release_all("p1") == 2
    assert c.holder_of("c") == "p2"


# ------------------------------------------------------- 四类粒子
def test_sensor_cannot_write_or_spawn():
    reg = ParticleRegistry()
    reg.spawn("s1", SENSOR)
    assert reg.check("s1", CAP_WRITE) is False
    with pytest.raises(PermissionError):
        reg.spawn("s1c", WORKER, parent="s1")


def test_guardian_can_veto_but_not_work():
    """守卫不能既当运动员又当裁判。"""
    reg = ParticleRegistry()
    reg.spawn("g1", GUARDIAN)
    assert reg.check("g1", CAP_VETO) is True
    assert reg.check("g1", CAP_WRITE) is False
    assert reg.check("g1", CAP_NET) is False


def test_worker_can_spawn_within_limit():
    reg = ParticleRegistry()
    reg.spawn("w0", WORKER)
    assert reg.check("w0", CAP_SPAWN) is True
    for i in range(8):
        reg.spawn(f"w0c{i}", WORKER, generation=1, parent="w0")
    with pytest.raises(PermissionError):
        reg.spawn("w0c8", WORKER, generation=1, parent="w0")


def test_archivist_writes_memory_only():
    reg = ParticleRegistry()
    reg.spawn("a1", ARCHIVIST)
    assert reg.check("a1", CAP_MEMORY_WRITE) is True
    assert reg.check("a1", CAP_WRITE) is False


def test_require_raises_with_useful_message():
    reg = ParticleRegistry()
    reg.spawn("s1", SENSOR)
    with pytest.raises(PermissionError) as e:
        reg.require("s1", CAP_WRITE)
    assert "无 write 权限" in str(e.value)


def test_kill_cascades_to_children():
    reg = ParticleRegistry()
    reg.spawn("w0", WORKER)
    reg.spawn("w1", WORKER, generation=1, parent="w0")
    reg.spawn("w2", WORKER, generation=2, parent="w1")
    assert reg.kill("w0") == 3
    assert len(reg) == 0


def test_unknown_type_rejected_and_census():
    reg = ParticleRegistry()
    with pytest.raises(ValueError):
        reg.spawn("x", "ghost")
    reg.spawn("s", SENSOR); reg.spawn("w", WORKER)
    assert reg.census() == {"sensor": 1, "worker": 1, "guardian": 0, "archivist": 0}
