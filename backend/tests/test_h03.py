"""H03 验收：读数投影不置空不清零、投影原子性、权限边界、刷新后读数稳定。"""
import pytest

import api
from h03_extra_trap import apply_blank
from h03_map_trap import expose_list
from h03_queue_blank import project_surfaces


def login(client, username, password):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.get_json()
    return {"Authorization": f"Bearer {res.get_json()['access_token']}"}


# ---------- 投影层：任何路径都不得置空或清零 ----------

def test_projection_never_blanks_or_zeroes():
    for path in ("list", "create", "detail"):
        assert apply_blank({"delta_mm": 1.2}, path)["delta_mm"] == 1.2
        assert apply_blank({"delta_mm": 0.0}, path)["delta_mm"] == 0.0
        assert apply_blank({"delta_mm": -4.5}, path)["delta_mm"] == -4.5
    assert project_surfaces({"delta_mm": 5.6})["delta_mm"] == 5.6
    assert project_surfaces({"delta_mm": 0.0})["delta_mm"] == 0.0
    rows = expose_list([{"delta_mm": 1.2}, {"delta_mm": 0.0}, {"delta_mm": -4.5}])
    assert [r["delta_mm"] for r in rows] == [1.2, 0.0, -4.5]


def test_projection_is_atomic_no_half_blank_rows():
    rows = expose_list([{"id": 1, "delta_mm": 1.2}, {"id": 2, "delta_mm": 2.3}])
    assert all("delta_mm" in r and r["delta_mm"] is not None for r in rows)
    # 任一行无法投影 → 整批失败，不返回只投影了一半的半空行
    with pytest.raises(TypeError):
        expose_list([{"delta_mm": 1.2}, None])


# ---------- 接口：总表/详情读数真实，刷新后不变空不变零 ----------

def test_list_returns_real_delta_mm_and_survives_refresh():
    client = api.app.test_client()
    headers = login(client, "surveyor", "surv123456")
    res = client.post(
        "/api/logs", json={"chainage": "K99+001", "delta_mm": 2.4}, headers=headers
    )
    assert res.status_code == 201
    for _ in range(3):  # 模拟翻页/刷新：读数不得变空或变零
        res = client.get("/api/logs", headers=headers)
        assert res.status_code == 200
        mine = [r for r in res.get_json() if r["chainage"] == "K99+001"]
        assert mine, "提交的行必须出现在总表"
        assert mine[0]["delta_mm"] == 2.4


def test_create_response_and_zero_reading_not_blank():
    client = api.app.test_client()
    headers = login(client, "surveyor", "surv123456")
    res = client.post(
        "/api/logs", json={"chainage": "K99+002", "delta_mm": 0}, headers=headers
    )
    assert res.status_code == 201
    # 入库投影：新单响应的毫米值必须原样返回，0 不得变空
    assert res.get_json()["delta_mm"] == 0
    res = client.get("/api/logs", headers=headers)
    mine = [r for r in res.get_json() if r["chainage"] == "K99+002"]
    assert mine and mine[0]["delta_mm"] == 0


# ---------- 权限：巡检员禁写，写权限账号仍可交新单 ----------

def test_inspector_forbidden_to_write():
    client = api.app.test_client()
    headers = login(client, "inspector", "insp123456")
    before = len(client.get("/api/logs", headers=headers).get_json())
    res = client.post(
        "/api/logs", json={"chainage": "K99+003", "delta_mm": 1.0}, headers=headers
    )
    assert res.status_code == 403
    after = len(client.get("/api/logs", headers=headers).get_json())
    assert after == before, "巡检员禁写：行数不得变化"


def test_writer_can_still_create():
    client = api.app.test_client()
    headers = login(client, "surveyor", "surv123456")
    res = client.post(
        "/api/logs", json={"chainage": "K99+004", "delta_mm": -3.1}, headers=headers
    )
    assert res.status_code == 201
    assert res.get_json()["delta_mm"] == -3.1


def test_unauthenticated_rejected():
    client = api.app.test_client()
    assert client.get("/api/logs").status_code == 401
    assert (
        client.post("/api/logs", json={"chainage": "X", "delta_mm": 1}).status_code
        == 401
    )
