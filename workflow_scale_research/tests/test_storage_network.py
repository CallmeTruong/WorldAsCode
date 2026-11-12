import concurrent.futures
import json
import time

import pytest

from worldscale.artifacts import AssetStore, Ledger, write_json
from worldscale.jobs import JobQueue
from worldscale.network import NetworkEdge, compatible_ports, tile_fragments, tile_owner


def test_boundary_uses_shared_global_stationing():
    edge = NetworkEdge("global-road", ((0, 0, 0), (200, 0, 0)), 8)
    a = edge.sample(100)
    b = edge.sample(100)
    assert compatible_ports(a, b)
    b["phase"] = 0
    assert not compatible_ports(a, b)
    assert tile_owner((100, 0, 0)) == (1, 0)
    assert tile_owner((-1, 0, 0)) == (-1, 0)
    for value in (-1, float("nan"), 201):
        with pytest.raises(ValueError):
            edge.sample(value)
    with pytest.raises(ValueError):
        NetworkEdge("x", ((0, 0, 0), (1, 0, 0)), float("nan"))
    with pytest.raises(ValueError):
        NetworkEdge("r", ((0, 0, 0), (1, 0, 0)), 2, kind="rail")


def test_multitile_ports_and_uv_phase_survive_curves():
    edge = NetworkEdge("road", ((-40, 0, 10), (250, 0, 10), (250, 2, 160)), 8)
    fragments = tile_fragments(edge)
    assert len(fragments) > 3
    assert fragments[0]["owner"] == (-1, 0)
    for a, b in zip(fragments, fragments[1:]):
        assert compatible_ports(a["end"], b["start"])
        assert a["uv_station"][1] == b["uv_station"][0]
    assert fragments[-1]["uv_station"][0] > 0
    assert any(f["references"] for f in fragments)


def test_parallel_asset_writes_are_atomic_and_corruption_is_detected(tmp_path):
    store = AssetStore(tmp_path)
    payload = {"geometry": "shape", "version": 1}
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        keys = list(pool.map(lambda _: store.put(payload), range(32)))
    assert len(set(keys)) == 1 and store.get(keys[0]) == payload
    p = tmp_path / (keys[0] + ".json")
    data = json.loads(p.read_text())
    data["payload"]["version"] = 2
    write_json(p, data)
    with pytest.raises(ValueError, match="HASH"):
        store.get(keys[0])


def test_queue_deduplicates_dependencies_and_fences_worker_leases(tmp_path):
    q = JobQueue(tmp_path / "queue.sqlite")
    a = q.enqueue({"node": "observe"})
    assert a == q.enqueue({"node": "observe"})
    b = q.enqueue({"node": "build"}, dependencies=[a], priority=10)
    first = q.claim()
    assert first["key"] == a and q.claim() is None
    out = tmp_path / "out.json"
    write_json(out, {"done": True})
    with pytest.raises(ValueError, match="LEASE"):
        q.finish(a, "wrong-lease", out)
    q.finish(a, first["lease"], out)
    second = q.claim()
    assert second["key"] == b
    q.heartbeat(b, second["lease"])
    q.fail(b, second["lease"], "strict-failed")
    assert q.claim() is None


def test_expired_paid_job_is_not_blindly_retried(tmp_path):
    q = JobQueue(tmp_path / "queue.sqlite")
    key = q.enqueue({"node": "paid-coder"})
    q.claim()
    with q.connect() as db:
        db.execute("UPDATE jobs SET expires=? WHERE key=?", (time.time() - 1, key))
    assert q.claim() is None
    with q.connect() as db:
        assert db.execute("SELECT status FROM jobs").fetchone()["status"] == "uncertain"


def test_only_preflight_budget_block_is_safe_to_requeue(tmp_path):
    q = JobQueue(tmp_path / "queue.sqlite")
    key = q.enqueue({"node": "model"})
    lease = q.claim()
    q.fail(key, lease["lease"], "BudgetExceeded: MODEL_BUDGET_EXHAUSTED")
    q.requeue_preflight_budget(key)
    assert q.get(key)["status"] == "pending"

    next_lease = q.claim()
    q.fail(key, next_lease["lease"], "HTTP_524; billing state uncertain")
    with pytest.raises(ValueError, match="NOT_SAFE_TO_REQUEUE"):
        q.requeue_preflight_budget(key)


def test_ledger_persists(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.event("gate", "blocked", reason="actual error")
    assert ledger.events()[0]["reason"] == "actual error"
