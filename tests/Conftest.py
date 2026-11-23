"""Фикстуры для интеграционных тестов ЛР3.

Требуется PostgreSQL (в моделях используется JSONB, SQLite не подойдёт).
Тесты работают с ОТДЕЛЬНОЙ базой (по умолчанию pipeline_db_test), которую нужно создать заранее:

    createdb -U postgres pipeline_db_test

Имя можно поменять переменной окружения TEST_DB_NAME. Таблицы создаются в начале
сессии, очищаются после каждого теста и удаляются в конце.

gRPC-сервис поднимается прямо внутри pytest (реальный AnalyticsServicer на свободном порту),
поэтому для обычных тестов отдельный процесс `python -m src.grpc_service.server` не нужен.
"""
import os
import socket
import uuid
from concurrent import futures
from types import SimpleNamespace

import grpc
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.api.crud_modules import job_crud
from src.api.dependencies import get_grpc_client
from src.api.grpc_client import AnalyticsGrpcClient
from src.api.main import app
from src.config import DB_HOST, DB_PASS, DB_PORT, DB_USER
from src.database import get_db
from src.grpc_generated import analytics_pb2_grpc
from src.grpc_service.handlers import HANDLERS
from src.grpc_service.servicer import AnalyticsServicer
from src.models.algorithm import Algorithm
from src.models.base import Base
from src.models.dataset import Dataset
from src.models.pipeline import Pipeline, PipelineStep

TEST_DB_NAME = os.getenv("TEST_DB_NAME", "pipeline_db_test")
TEST_DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{TEST_DB_NAME}"

PASSWORD = "Str0ng-Passw0rd!"


# ---------------------------------------------------------------- БД


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def _clean_db(engine):
    yield
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------- gRPC


@pytest.fixture(scope="session")
def grpc_port():
    """Реальный AnalyticsServicer в этом же процессе, порт выбирает ОС."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    analytics_pb2_grpc.add_AnalyticsServiceServicer_to_server(AnalyticsServicer(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    yield port
    server.stop(0)


@pytest.fixture
def grpc_client(grpc_port):
    client = AnalyticsGrpcClient("127.0.0.1", grpc_port, timeout=5.0)
    yield client
    client.close()


@pytest.fixture
def dead_grpc_client():
    """Клиент к порту, на котором никто не слушает (имитация незапущенного gRPC-сервера)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    client = AnalyticsGrpcClient("127.0.0.1", free_port, timeout=2.0)
    yield client
    client.close()


# ---------------------------------------------------------------- HTTP-клиент


@pytest.fixture
def client(session_factory, grpc_client):
    """TestClient (httpx) с подменёнными БД и gRPC-клиентом (по умолчанию - рабочий сервер)."""

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_grpc_client] = lambda: grpc_client
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def use_grpc_client(client):
    """Подменить gRPC-клиент внутри конкретного теста: use_grpc_client(fake)."""

    def _use(replacement) -> None:
        app.dependency_overrides[get_grpc_client] = lambda: replacement

    return _use


# ---------------------------------------------------------------- пользователи


def _create_user(client: TestClient, prefix: str) -> SimpleNamespace:
    """Регистрация через POST /register и логин через POST /login (OAuth2 form)."""
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, f"register failed: {r.status_code} {r.text}"
    user_id = r.json()["id"]
    r = client.post("/login", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json()["access_token"]
    return SimpleNamespace(
        id=user_id,
        email=email,
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.fixture
def user(client):
    return _create_user(client, "owner")


@pytest.fixture
def other_user(client):
    return _create_user(client, "other")


# ---------------------------------------------------------------- фабрики данных


@pytest.fixture
def make_dataset(db):
    def _make(user_id: int, rows: int = 100) -> Dataset:
        ds = Dataset(
            user_id=user_id,
            name=f"dataset_{uuid.uuid4().hex[:6]}.csv",
            file_path="uploads/test.csv",
            row_count=rows,
            file_size_bytes=1024,
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)
        return ds

    return _make


@pytest.fixture
def make_pipeline(db):
    """Конвейер из `steps` шагов (0 - пустой конвейер). Используются реальные хендлеры из HANDLERS."""

    def _make(user_id: int, steps: int = 2, published: bool = False) -> Pipeline:
        handlers = sorted(HANDLERS)
        pipeline = Pipeline(title="Test pipeline", created_by=user_id, is_published=published)
        db.add(pipeline)
        db.flush()
        for order in range(1, steps + 1):
            algo = Algorithm(
                code=f"test_algo_{uuid.uuid4().hex[:8]}",
                name=f"Test algorithm {order}",
                grpc_handler=handlers[(order - 1) % len(handlers)],
                default_params={},
                is_active=True,
            )
            db.add(algo)
            db.flush()
            db.add(PipelineStep(pipeline_id=pipeline.id, algorithm_id=algo.id, step_order=order, step_params={}))
        db.commit()
        db.refresh(pipeline)
        return pipeline

    return _make


@pytest.fixture
def make_job(db, make_dataset, make_pipeline):
    """PENDING-задача пользователя с датасетом и конвейером. Возвращает (job, dataset, pipeline)."""

    def _make(user_id: int, steps: int = 2):
        dataset = make_dataset(user_id)
        pipeline = make_pipeline(user_id, steps=steps)
        job = job_crud.create_job(db, user_id, dataset.id, pipeline.id)
        return job, dataset, pipeline

    return _make