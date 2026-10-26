"""Проверка части A одним запуском (без PostgreSQL, на in-memory SQLite):

    python -m pytest -v tests/test_part_a.py

Пайплайны, нужные для задач, создаются напрямую через ORM, поэтому тест
не зависит от роутеров участника B.
"""
import uuid

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
from src.models import Algorithm, Base, Dataset, Pipeline, PipelineStep, ProcessingJob, User

CSV = b"a,b\n1,2\n3,4\n5,6\n"  # заголовок + 3 строки данных


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):
    return "JSON"


# ---------- фикстуры ----------

@pytest.fixture()
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        db.add(User(email="admin@test.io", hashed_password=hash_password("AdminPass1"), role="ADMIN"))
        db.commit()
    return factory


@pytest.fixture()
def client(Session, tmp_path, monkeypatch):
    monkeypatch.setattr("src.api.routers.datasets.UPLOAD_DIR", tmp_path / "uploads")

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


def _login(client, email, password):
    r = client.post("/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(client, email):
    r = client.post("/register", json={"email": email, "password": "ClientPass1"})
    assert r.status_code == 201, r.text
    return _login(client, email, "ClientPass1")


@pytest.fixture()
def admin(client):
    return _login(client, "admin@test.io", "AdminPass1")


@pytest.fixture()
def alice(client):
    return _register(client, "alice@test.io")


@pytest.fixture()
def bob(client):
    return _register(client, "bob@test.io")


def _upload(client, headers, name="Sales", filename="data.csv", content=CSV):
    return client.post("/datasets", headers=headers, data={"name": name}, files={"file": (filename, content, "text/csv")})


def _seed_pipeline(Session, published=True, created_by=None):
    """Создаёт алгоритм и пайплайн с одним шагом напрямую в БД (без роутеров B)."""
    with Session() as db:
        algo = Algorithm(code=f"algo-{uuid.uuid4().hex[:6]}", name="Algo", grpc_handler="Handler", default_params={})
        db.add(algo)
        db.flush()
        pipeline = Pipeline(
            title="Test pipeline",
            is_published=published,
            created_by=created_by,
            steps=[PipelineStep(algorithm_id=algo.id, step_order=1, step_params={})],
        )
        db.add(pipeline)
        db.commit()
        return pipeline.id


def _complete_job(Session, job_id, result):
    with Session() as db:
        job = db.get(ProcessingJob, job_id)
        job.status = "COMPLETED"
        job.result_data = result
        db.commit()


# ---------- шаг 1–4: регистрация, вход, JWT ----------

def test_register_login_me(client):
    token = _register(client, "alice@test.io")
    me = client.get("/users/me", headers=token).json()
    assert me["email"] == "alice@test.io" and me["role"] == "CLIENT"


def test_register_ignores_role_and_hides_password(client):
    r = client.post("/register", json={"email": "evil@test.io", "password": "ClientPass1", "role": "ADMIN"})
    assert r.status_code == 201
    assert r.json()["role"] == "CLIENT"
    assert "password" not in r.text and "hashed" not in r.text


def test_register_validation(client):
    assert client.post("/register", json={"email": "not-an-email", "password": "ClientPass1"}).status_code == 422
    assert client.post("/register", json={"email": "a@test.io", "password": "short"}).status_code == 422


def test_register_password_over_72_bytes(client):
    # 40 кириллических букв = 80 байт: раньше bcrypt падал, и API отвечал 500
    r = client.post("/register", json={"email": "ru@test.io", "password": "я" * 40})
    assert r.status_code == 422
    # 36 букв = ровно 72 байта: допустимо, и вход работает
    ok = {"email": "ru2@test.io", "password": "я" * 36}
    assert client.post("/register", json=ok).status_code == 201
    assert client.post("/login", data={"username": ok["email"], "password": ok["password"]}).status_code == 200


def test_register_duplicate_email(client, alice):
    r = client.post("/register", json={"email": "ALICE@test.io", "password": "ClientPass1"})
    assert r.status_code == 409


def test_login_wrong_password_or_user(client, alice):
    assert client.post("/login", data={"username": "alice@test.io", "password": "wrong-pass"}).status_code == 401
    assert client.post("/login", data={"username": "ghost@test.io", "password": "ClientPass1"}).status_code == 401


def test_protected_endpoints_need_valid_token(client):
    assert client.get("/users/me").status_code == 401
    assert client.get("/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/datasets").status_code == 401
    assert client.get("/jobs").status_code == 401


# ---------- шаг 5: пользователи и роли ----------

def test_users_list_is_admin_only(client, admin, alice):
    assert client.get("/users", headers=alice).status_code == 403
    assert len(client.get("/users", headers=admin).json()) == 2


def test_change_role(client, admin, alice, bob):
    assert client.patch("/users/2/role", headers=alice, json={"role": "ADMIN"}).status_code == 403
    assert client.patch("/users/1/role", headers=admin, json={"role": "CLIENT"}).status_code == 400  # себе нельзя
    assert client.patch("/users/999/role", headers=admin, json={"role": "ADMIN"}).status_code == 404
    assert client.patch("/users/2/role", headers=admin, json={"role": "SUPERUSER"}).status_code == 422
    assert client.patch("/users/3/role", headers=admin, json={"role": "ADMIN"}).json()["role"] == "ADMIN"
    assert client.get("/users", headers=bob).status_code == 200  # права сменились без перелогина


# ---------- шаг 6: датасеты ----------

def test_dataset_upload_counts_rows(client, alice):
    r = _upload(client, alice)
    assert r.status_code == 201, r.text
    ds = r.json()
    assert ds["row_count"] == 3
    assert ds["file_size_bytes"] == len(CSV)
    assert "file_path" not in ds  # внутренний путь не раскрывается


def test_dataset_upload_without_trailing_newline(client, alice):
    assert _upload(client, alice, content=b"a,b\n1,2\n3,4").json()["row_count"] == 2


def test_dataset_upload_rejections(client, alice, admin):
    assert _upload(client, alice, filename="virus.exe").status_code == 400
    assert _upload(client, alice, content=b"").status_code == 400
    assert _upload(client, admin).status_code == 403  # загружает только CLIENT
    assert client.post("/datasets", headers=alice, files={"file": ("d.csv", CSV, "text/csv")}).status_code == 422  # нет name


def test_dataset_file_saved_on_disk(client, alice, tmp_path):
    _upload(client, alice)
    saved = list((tmp_path / "uploads").rglob("*.csv"))
    assert len(saved) == 1 and saved[0].read_bytes() == CSV


def test_dataset_isolation_between_clients(client, alice, bob, admin):
    ds_id = _upload(client, alice).json()["id"]
    assert client.get(f"/datasets/{ds_id}", headers=bob).status_code == 404
    assert client.put(f"/datasets/{ds_id}", headers=bob, json={"name": "hack"}).status_code == 404
    assert client.delete(f"/datasets/{ds_id}", headers=bob).status_code == 404
    assert client.get("/datasets", headers=bob).json() == []
    assert len(client.get("/datasets", headers=alice).json()) == 1
    assert client.get(f"/datasets/{ds_id}", headers=admin).status_code == 200  # админ видит всё
    assert len(client.get("/datasets", headers=admin).json()) == 1
    assert client.put(f"/datasets/{ds_id}", headers=admin, json={"name": "x"}).status_code == 404  # но не меняет чужое


def test_dataset_update_and_delete(client, alice, tmp_path):
    ds_id = _upload(client, alice).json()["id"]
    assert client.put(f"/datasets/{ds_id}", headers=alice, json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert client.put(f"/datasets/{ds_id}", headers=alice, json={"name": ""}).status_code == 422
    assert client.delete(f"/datasets/{ds_id}", headers=alice).status_code == 204
    assert client.get(f"/datasets/{ds_id}", headers=alice).status_code == 404
    assert list((tmp_path / "uploads").rglob("*.csv")) == []  # файл удалён с диска


# ---------- шаг 7: задачи ----------

def test_job_lifecycle(client, Session, alice, bob, admin):
    ds_id = _upload(client, alice).json()["id"]
    pipe_id = _seed_pipeline(Session)

    r = client.post("/jobs", headers=alice, json={"dataset_id": ds_id, "pipeline_id": pipe_id})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "PENDING" and job["current_step"] == 0 and job["finished_at"] is None

    assert client.get(f"/jobs/{job['id']}/result", headers=alice).status_code == 409  # ещё не готово
    assert client.get(f"/jobs/{job['id']}", headers=bob).status_code == 404            # чужая
    assert client.get(f"/jobs/{job['id']}", headers=admin).status_code == 200          # админ видит

    _complete_job(Session, job["id"], {"mean": 3.0})
    r = client.get(f"/jobs/{job['id']}/result", headers=alice)
    assert r.status_code == 200 and r.json()["result"] == {"mean": 3.0}

    assert [j["id"] for j in client.get("/jobs", headers=alice).json()] == [job["id"]]
    assert client.get("/jobs", params={"status": "PENDING"}, headers=alice).json() == []
    assert client.get("/jobs", headers=bob).json() == []


def test_job_creation_rules(client, Session, alice, bob, admin):
    ds_id = _upload(client, alice).json()["id"]
    published = _seed_pipeline(Session, published=True)
    draft_of_other = _seed_pipeline(Session, published=False, created_by=1)  # черновик админа

    assert client.post("/jobs", headers=bob, json={"dataset_id": ds_id, "pipeline_id": published}).status_code == 404  # чужой датасет
    assert client.post("/jobs", headers=alice, json={"dataset_id": ds_id, "pipeline_id": draft_of_other}).status_code == 404  # чужой черновик
    assert client.post("/jobs", headers=alice, json={"dataset_id": 999, "pipeline_id": published}).status_code == 404
    assert client.post("/jobs", headers=alice, json={"dataset_id": ds_id, "pipeline_id": 999}).status_code == 404
    assert client.post("/jobs", headers=alice, json={"dataset_id": ds_id}).status_code == 422
    assert client.post("/jobs", headers=admin, json={"dataset_id": ds_id, "pipeline_id": published}).status_code == 403


def test_job_blocks_dataset_delete_and_can_be_deleted(client, Session, alice):
    ds_id = _upload(client, alice).json()["id"]
    pipe_id = _seed_pipeline(Session)
    job_id = client.post("/jobs", headers=alice, json={"dataset_id": ds_id, "pipeline_id": pipe_id}).json()["id"]

    assert client.delete(f"/datasets/{ds_id}", headers=alice).status_code == 409
    assert client.delete(f"/jobs/{job_id}", headers=alice).status_code == 204
    assert client.get(f"/jobs/{job_id}", headers=alice).status_code == 404
    assert client.delete(f"/datasets/{ds_id}", headers=alice).status_code == 204
