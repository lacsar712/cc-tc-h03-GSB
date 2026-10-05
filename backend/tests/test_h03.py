"""H03 验收：毫米读数从入库投影到总表再到详情，全程不能凭空变空或变零。

用 SQLite 内存库跑真实的 Flask 路由与认领投影逻辑（claimer 后台线程关闭，
claim_once 由测试显式驱动，保证可重复）。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["DATABASE_URL"] = "sqlite://"

import models  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# 进程内认领线程在测试里不启动，claim_once 由用例显式调用。
import claimer  # noqa: E402

claimer.start = lambda: None

import api  # noqa: E402
from models import ConvergenceLog  # noqa: E402

# api 在导入时已 seed 建表；换成测试专用的内存引擎并重建结构。
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
models.engine = test_engine
api.engine = test_engine
TestSession = sessionmaker(bind=test_engine)
models.SessionLocal = TestSession
api.SessionLocal = TestSession
# claimer 通过 `from models import SessionLocal` 按值持有引用，需单独替换。
claimer.SessionLocal = TestSession
models.Base.metadata.create_all(test_engine)


REQUIRED_FIELDS = {"id", "chainage", "delta_mm", "status", "created_by", "created_at"}


@pytest.fixture
def client():
    db = TestSession()
    db.query(ConvergenceLog).delete()
    db.commit()
    db.close()
    api.app.testing = True
    return api.app.test_client()


def token(client, username, password):
    res = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert res.status_code == 200, res.get_json()
    return res.get_json()["access_token"]


def auth(client, username, password):
    return {"Authorization": f"Bearer {token(client, username, password)}"}


def assert_complete(row):
    """每行字段必须完整：核心字段不许缺、不许为 None，杜绝半空行。"""
    assert REQUIRED_FIELDS <= set(row), f"缺字段: {row}"
    for key in REQUIRED_FIELDS:
        assert row[key] is not None, f"{key} 无故为空: {row}"
    assert isinstance(row["delta_mm"], (int, float)), f"毫米数不是数字: {row}"


def submit(client, headers, chainage, delta):
    return client.post(
        "/api/logs", json={"chainage": chainage, "delta_mm": delta}, headers=headers
    )


# ---------- 写权限账号仍可交新单，回显真实值（含 0.0 与负值） ----------


@pytest.mark.parametrize("delta", [1.2, 0.0, -0.0, -2.5, -5.6, 3.0])
def test_writer_submit_echoes_true_value(client, delta):
    h = auth(client, "surveyor", "surv123456")
    res = submit(client, h, "K20+050", delta)
    assert res.status_code == 201, res.get_json()
    data = res.get_json()
    assert_complete(data)
    assert data["delta_mm"] == pytest.approx(delta)
    assert data["status"] == "pending"
    assert data["chainage"] == "K20+050"


# ---------- 翻页与反复刷新后，读数不能变空或变零 ----------


def test_refresh_and_pagination_keep_values(client):
    h = auth(client, "surveyor", "surv123456")
    submitted = {"K01": 1.2, "K02": 0.0, "K03": -2.5, "K04": 5.6, "K05": -0.3}
    for chainage, delta in submitted.items():
        assert submit(client, h, chainage, delta).status_code == 201

    seen = {}
    # 逐页拉取，模拟翻页；每页每行都必须完整且值正确。
    for offset in range(0, len(submitted), 2):
        res = client.get(f"/api/logs?limit=2&offset={offset}", headers=h)
        assert res.status_code == 200
        page = res.get_json()
        assert page, "翻页不应出现空白页"
        for row in page:
            assert_complete(row)
            assert row["delta_mm"] == pytest.approx(submitted[row["chainage"]])
            seen[row["chainage"]] = row["delta_mm"]
    assert set(seen) == set(submitted)

    # 再整体刷新两次（页面 2 秒轮询的等价场景），值必须纹丝不动。
    snapshots = []
    for _ in range(2):
        res = client.get("/api/logs", headers=h)
        assert res.status_code == 200
        rows = res.get_json()
        assert len(rows) == len(submitted)
        for row in rows:
            assert_complete(row)
            assert row["delta_mm"] == pytest.approx(submitted[row["chainage"]])
        snapshots.append({r["id"]: r["delta_mm"] for r in rows})
    assert snapshots[0] == snapshots[1]


# ---------- 总表走到详情，读数一致，不为空/零 ----------


def test_detail_matches_list_and_db(client):
    h = auth(client, "surveyor", "surv123456")
    log_id = submit(client, h, "K30+000", 0.0).get_json()["id"]

    res = client.get(f"/api/logs/{log_id}", headers=h)
    assert res.status_code == 200
    detail = res.get_json()
    assert_complete(detail)
    assert detail["delta_mm"] == 0.0
    assert detail["id"] == log_id

    listed = [r for r in client.get("/api/logs", headers=h).get_json() if r["id"] == log_id]
    assert len(listed) == 1
    assert listed[0]["delta_mm"] == detail["delta_mm"] == 0.0

    assert client.get("/api/logs/999999", headers=h).status_code == 404


# ---------- 投影做到一半失败，不能留下半空行：回滚后原样可重试 ----------


def test_failed_claim_rolls_back_and_retry_succeeds(client, monkeypatch):
    h = auth(client, "surveyor", "surv123456")
    log_id = submit(client, h, "K40+100", 2.2).get_json()["id"]

    import rules

    def boom(_delta):
        raise RuntimeError("judge 投影中途失败")

    monkeypatch.setattr(rules, "judge", boom)
    # claimer.claim_once 内用的是 `from rules import judge` 绑定的名字
    monkeypatch.setattr(claimer, "judge", boom)

    with pytest.raises(RuntimeError):
        claimer.claim_once()

    db = TestSession()
    row = db.get(ConvergenceLog, log_id)
    # 事务整体回滚：行保持待处理，投影字段全空，毫米读数原样保留。
    assert row.status == "pending"
    assert row.verdict is None
    assert row.reason is None
    assert row.processed_at is None
    assert row.delta_mm == pytest.approx(2.2)
    db.close()

    monkeypatch.undo()
    assert claimer.claim_once() is True
    db = TestSession()
    row = db.get(ConvergenceLog, log_id)
    assert row.status == "done"
    assert row.verdict == "合格"
    assert row.reason is not None
    assert row.processed_at is not None
    assert row.delta_mm == pytest.approx(2.2)
    db.close()

    # 投影完成后的总表与详情依旧带着真实毫米数与全部字段。
    listed = client.get("/api/logs", headers=h).get_json()
    row = next(r for r in listed if r["id"] == log_id)
    assert_complete(row)
    assert row["delta_mm"] == pytest.approx(2.2)
    detail = client.get(f"/api/logs/{log_id}", headers=h).get_json()
    assert detail["verdict"] == "合格"
    assert detail["delta_mm"] == pytest.approx(2.2)


# ---------- 判定规则：0 与负值不被当作异常 ----------


@pytest.mark.parametrize(
    "delta,verdict",
    [(0.0, "合格"), (-2.5, "合格"), (3.0, "合格"), (-3.0, "合格"), (3.1, "超限"), (-5.6, "超限")],
)
def test_judge_rules(client, delta, verdict):
    from rules import judge

    assert judge(delta)[0] == verdict


# ---------- 巡检员禁写，但可读 ----------


def test_inspector_forbidden_to_submit_but_can_read(client):
    hi = auth(client, "inspector", "insp123456")
    res = submit(client, hi, "K99+999", 1.0)
    assert res.status_code == 403

    hw = auth(client, "surveyor", "surv123456")
    submit(client, hw, "K50+000", 1.8)

    res = client.get("/api/logs", headers=hi)
    assert res.status_code == 200
    rows = res.get_json()
    assert any(r["chainage"] == "K50+000" for r in rows)
    for row in rows:
        assert_complete(row)


# ---------- 未登录一律 401 ----------


@pytest.mark.parametrize("method,path", [("get", "/api/logs"), ("post", "/api/logs")])
def test_anonymous_rejected(client, method, path):
    fn = getattr(client, method)
    res = fn(path) if method == "get" else fn(path, json={"chainage": "x", "delta_mm": 1})
    assert res.status_code == 401


def test_anonymous_detail_rejected(client):
    assert client.get("/api/logs/1").status_code == 401


# ---------- 入参校验：脏数据挡在库外，不会写入半空行 ----------


def test_invalid_payloads_rejected(client):
    h = auth(client, "surveyor", "surv123456")
    assert submit(client, h, "  ", 1.0).status_code == 400
    assert submit(client, h, "K60+000", "abc").status_code == 400
    assert submit(client, h, "K60+000", None).status_code == 400
    assert submit(client, h, "K60+000", True).status_code == 400
    # 裸 NaN / 非对象体必须被挡在库外，不能落成半空行。
    bad_json = client.post(
        "/api/logs",
        data="NaN",
        headers={**h, "Content-Type": "application/json"},
    )
    assert bad_json.status_code == 400
    rows = client.get("/api/logs", headers=h).get_json()
    assert rows == []
