import math
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from claimer import start as start_claimer
from models import Base, ConvergenceLog, SessionLocal, engine, row_dict

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(ConvergenceLog).count() > 0:
            return
        now = datetime.now(timezone.utc)
        for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
            from rules import judge

            verdict, reason = judge(delta)
            assert verdict == expect
            db.add(
                ConvergenceLog(
                    chainage=chainage,
                    delta_mm=delta,
                    status="done",
                    verdict=verdict,
                    reason=reason,
                    created_by="surveyor",
                    created_at=now,
                    processed_at=now,
                )
            )
        db.commit()
    finally:
        db.close()


seed()
start_claimer()


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "role": payload.get("role")}


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_writer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "仅测量员可提交收敛读数"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"detail": "用户名或密码错误"}), 401
    raw_username = body.get("username")
    username = raw_username.strip() if isinstance(raw_username, str) else ""
    password = body.get("password") if isinstance(body.get("password"), str) else ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        return jsonify({"detail": "用户名或密码错误"}), 401
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return jsonify({"access_token": token, "username": username, "role": user["role"]})


@app.get("/api/logs")
@require_login
def list_logs():
    # 可选翻页：?limit=&offset=；不传则返回全部（保持原有顺序，新单在前）。
    try:
        limit = int(request.args.get("limit")) if request.args.get("limit") is not None else None
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return jsonify({"detail": "limit/offset 必须是非负整数"}), 400
    if (limit is not None and limit < 1) or offset < 0:
        return jsonify({"detail": "limit/offset 必须是非负整数"}), 400
    db = SessionLocal()
    try:
        query = (
            db.query(ConvergenceLog)
            .order_by(ConvergenceLog.id.desc())
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(min(limit, 200))
        rows = query.all()
        # row_dict 是纯函数：每行要么完整序列化，要么整体抛错，绝不返回半空行。
        return jsonify([row_dict(r) for r in rows])
    finally:
        db.close()


@app.get("/api/logs/<int:log_id>")
@require_login
def get_log(log_id: int):
    db = SessionLocal()
    try:
        row = db.get(ConvergenceLog, log_id)
        if row is None:
            return jsonify({"detail": "记录不存在"}), 404
        return jsonify(row_dict(row))
    finally:
        db.close()


@app.post("/api/logs")
@require_writer
def create_log():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"detail": "请求体必须是 JSON 对象"}), 400
    raw_chainage = body.get("chainage")
    chainage = raw_chainage.strip() if isinstance(raw_chainage, str) else ""
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    raw_delta = body.get("delta_mm")
    if not isinstance(raw_delta, (int, float)) or isinstance(raw_delta, bool):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    delta_mm = float(raw_delta)
    if not math.isfinite(delta_mm):
        return jsonify({"detail": "收敛值必须是有限数字"}), 400
    db = SessionLocal()
    try:
        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=delta_mm,
            status="pending",
            created_by=g.user["username"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    finally:
        db.close()
