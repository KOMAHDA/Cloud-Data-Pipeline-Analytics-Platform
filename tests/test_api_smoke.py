"""Сквозной смоук-тест лабы 2.

Работает на in-memory SQLite (JSONB подменяется на JSON только в тесте),
поэтому PostgreSQL для запуска не нужен:  pytest -q
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.api.security import hash_password
from src.database import get_db
from src.models import Base, User


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):
    return "JSON"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("src.api.routers.datasets.UPLOAD_DIR", tmp_path / "uploads")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add(User(email="admin@test.io", hashed_password=hash_password("AdminPass1"), role="ADMIN"))
        db.commit()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(client, email, password):
    r = client.post("/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def register(client, email, password="ClientPass1"):
    r = client.post("/register", json={"email": email, "password": password, "role": "ADMIN"})
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "CLIENT"  # роль из тела запроса игнорируется
    assert "hashed_password" not in r.json()
    return login(client, email, password)


def test_full_scenario(client):
    # --- аутентификация ---
    assert client.get("/users/me").status_code == 401
    alice = register(client, "alice@test.io")
    bob = register(client, "bob@test.io")
    assert client.post("/register", json={"email": "alice@test.io", "password": "ClientPass1"}).status_code == 409
    assert client.post("/login", data={"username": "alice@test.io", "password": "wrong"}).status_code == 401
    admin = login(client, "admin@test.io", "AdminPass1")
    assert client.get("/users/me", headers=alice).json()["email"] == "alice@test.io"

    # --- роли ---
    assert client.get("/users", headers=alice).status_code == 403
    assert len(client.get("/users", headers=admin).json()) == 3
    assert client.post("/algorithms", headers=alice, json={}).status_code == 403

    # --- каталог алгоритмов (ADMIN) ---
    algo_payload = {"code": "normalize", "name": "Normalization", "grpc_handler": "Normalize", "default_params": {"m": "z"}}
    r = client.post("/algorithms", headers=admin, json=algo_payload)
    assert r.status_code == 201, r.text
    a1 = r.json()["id"]
    assert client.post("/algorithms", headers=admin, json=algo_payload).status_code == 409
    a2 = client.post(
        "/algorithms", headers=admin,
        json={"code": "outliers", "name": "Outliers", "grpc_handler": "Outliers"},
    ).json()["id"]
    r = client.put(f"/algorithms/{a2}", headers=admin, json={"description": "IQR filter"})
    assert r.status_code == 200 and r.json()["description"] == "IQR filter"
    assert len(client.get("/algorithms", headers=alice).json()) == 2

    # --- пайплайн ---
    steps = [
        {"algorithm_id": a2, "step_order": 2, "step_params": {"k": 1.5}},
        {"algorithm_id": a1, "step_order": 1},
    ]
    assert client.post("/pipelines", headers=admin, json={"title": "bad", "steps": [steps[0], steps[0]]}).status_code == 422
    assert client.post("/pipelines", headers=admin, json={"title": "bad", "steps": [{"algorithm_id": 999, "step_order": 1}]}).status_code == 422
    r = client.post("/pipelines", headers=admin, json={"title": "Preprocessing", "steps": steps})
    assert r.status_code == 201, r.text
    pipe = r.json()
    assert [s["step_order"] for s in pipe["steps"]] == [1, 2]  # порядок гарантирован
    assert pipe["steps"][0]["algorithm"]["code"] == "normalize"
    assert pipe["is_published"] is False
    assert client.get(f"/pipelines/{pipe['id']}", headers=alice).status_code == 404  # черновик скрыт
    assert client.post(f"/pipelines/{pipe['id']}/publish", headers=alice).status_code == 403
    assert client.post(f"/pipelines/{pipe['id']}/publish", headers=admin).json()["is_published"] is True
    assert len(client.get("/pipelines", headers=alice).json()) == 1

    # --- датасеты ---
    csv = b"a,b\n1,2\n3,4\n5,6\n"
    files = {"file": ("data.csv", csv, "text/csv")}
    assert client.post("/datasets", headers=admin, data={"name": "x"}, files=files).status_code == 403
    assert client.post("/datasets", headers=alice, data={"name": "x"}, files={"file": ("a.exe", b"zz", "x/y")}).status_code == 400
    r = client.post("/datasets", headers=alice, data={"name": "Sales"}, files=files)
    assert r.status_code == 201, r.text
    ds = r.json()
    assert ds["row_count"] == 3 and ds["file_size_bytes"] == len(csv) and "file_path" not in ds
    assert client.get(f"/datasets/{ds['id']}", headers=bob).status_code == 404  # чужой
    assert client.get(f"/datasets/{ds['id']}", headers=admin).status_code == 200
    assert client.get("/datasets", headers=bob).json() == []
    assert client.put(f"/datasets/{ds['id']}", headers=alice, json={"name": "Sales 2026"}).json()["name"] == "Sales 2026"

    # --- задачи ---
    assert client.post("/jobs", headers=bob, json={"dataset_id": ds["id"], "pipeline_id": pipe["id"]}).status_code == 404
    r = client.post("/jobs", headers=alice, json={"dataset_id": ds["id"], "pipeline_id": pipe["id"]})
    assert r.status_code == 201 and r.json()["status"] == "PENDING"
    job = r.json()["id"]
    assert client.get(f"/jobs/{job}/result", headers=alice).status_code == 409
    assert client.get(f"/jobs/{job}", headers=bob).status_code == 404
    assert client.patch(f"/admin/jobs/{job}/status", headers=alice, json={"status": "COMPLETED"}).status_code == 403
    r = client.patch(
        f"/admin/jobs/{job}/status", headers=admin,
        json={"status": "COMPLETED", "current_step": 2, "result_data": {"mean": 3.0}},
    )
    assert r.status_code == 200 and r.json()["finished_at"] is not None
    r = client.get(f"/jobs/{job}/result", headers=alice)
    assert r.status_code == 200 and r.json()["result"] == {"mean": 3.0}
    assert len(client.get("/jobs", headers=alice).json()) == 1
    assert client.get("/jobs", headers=bob).json() == []
    assert len(client.get("/admin/jobs", headers=admin, params={"user_id": 2, "status": "COMPLETED"}).json()) == 1
    assert client.get("/admin/jobs", headers=alice).status_code == 403

    # --- целостность ---
    assert client.delete(f"/datasets/{ds['id']}", headers=alice).status_code == 409
    assert client.delete(f"/pipelines/{pipe['id']}", headers=admin).status_code == 409
    assert client.put(f"/pipelines/{pipe['id']}", headers=admin, json={"steps": steps}).status_code == 409
    assert client.delete(f"/jobs/{job}", headers=alice).status_code == 204
    assert client.delete(f"/datasets/{ds['id']}", headers=alice).status_code == 204

    # --- собственный пайплайн клиента ---
    r = client.post("/pipelines", headers=alice, json={"title": "Mine", "steps": [{"algorithm_id": a1, "step_order": 1}]})
    assert r.status_code == 201
    mine = r.json()["id"]
    assert client.get(f"/pipelines/{mine}", headers=bob).status_code == 404
    assert client.put(f"/pipelines/{pipe['id']}", headers=alice, json={"title": "hack"}).status_code == 403
    r = client.put(f"/pipelines/{mine}", headers=alice, json={"title": "Renamed", "steps": steps})
    assert r.status_code == 200 and r.json()["title"] == "Renamed" and len(r.json()["steps"]) == 2
    assert client.delete(f"/pipelines/{mine}", headers=alice).status_code == 204

    # --- мягкое удаление алгоритма ---
    assert client.delete(f"/algorithms/{a1}", headers=admin).status_code == 204
    assert client.get(f"/algorithms/{a1}", headers=alice).status_code == 404
    assert client.get(f"/algorithms/{a1}", headers=admin).status_code == 200
    assert client.post("/pipelines", headers=alice, json={"title": "x", "steps": [{"algorithm_id": a1, "step_order": 1}]}).status_code == 422

    # --- смена роли ---
    assert client.patch("/users/1/role", headers=admin, json={"role": "CLIENT"}).status_code == 400  # себе нельзя
    assert client.patch("/users/3/role", headers=admin, json={"role": "ADMIN"}).json()["role"] == "ADMIN"
    assert client.get("/users", headers=bob).status_code == 200  # права действуют сразу
