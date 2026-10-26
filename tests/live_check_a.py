"""Живая проверка части A: запущенный сервер + реальная PostgreSQL.

1. Запустите сервер:   uvicorn src.api.main:app
2. Админ уже создан:   python -m src.scripts.create_admin admin@example.com StrongPass123
3. Из корня проекта:   python -m tests.live_check_a admin@example.com StrongPass123 [http://localhost:8000]

Скрипт создаёт временного клиента, тестовый алгоритм и пайплайн, проходит весь
сценарий и в конце всё за собой удаляет.
"""
import shutil
import sys
import uuid

import httpx

from src.api.settings import UPLOAD_DIR
from src.database import SessionLocal
from src.models import Algorithm, Pipeline, PipelineStep, ProcessingJob, User

BASE = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8000"
CSV = b"a,b\n1,2\n3,4\n5,6\n"
failed: list[str] = []


def check(name: str, condition: bool, details: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + ("" if condition else f"   -> {details}"))
    if not condition:
        failed.append(name)


def bearer(c: httpx.Client, email: str, password: str) -> dict:
    r = c.post("/login", data={"username": email, "password": password})
    return {"Authorization": f"Bearer {r.json().get('access_token', '')}"}


def cleanup(user_id, pipeline_id, algo_id) -> None:
    with SessionLocal() as db:
        if user_id:
            db.query(ProcessingJob).filter(ProcessingJob.user_id == user_id).delete()
        if pipeline_id:
            db.query(ProcessingJob).filter(ProcessingJob.pipeline_id == pipeline_id).delete()
            pipeline = db.get(Pipeline, pipeline_id)
            if pipeline:
                db.delete(pipeline)
        db.commit()
        if algo_id:
            algo = db.get(Algorithm, algo_id)
            if algo:
                db.delete(algo)
        if user_id:
            user = db.get(User, user_id)
            if user:
                db.delete(user)
        db.commit()
    if user_id:
        shutil.rmtree(UPLOAD_DIR / str(user_id), ignore_errors=True)


def main() -> int:
    admin_email, admin_password = sys.argv[1], sys.argv[2]
    suffix = uuid.uuid4().hex[:8]
    email, password = f"live_{suffix}@example.com", "LivePass123"
    user_id = pipeline_id = algo_id = None

    with httpx.Client(base_url=BASE, timeout=30) as c:
        try:
            r = c.get("/health")
            check("сервер отвечает (/health)", r.status_code == 200, r.text)

            # --- регистрация и вход ---
            r = c.post("/register", json={"email": email, "password": password, "role": "ADMIN"})
            check("POST /register -> 201, роль CLIENT (поле role из тела игнорируется)",
                  r.status_code == 201 and r.json().get("role") == "CLIENT", r.text)
            user_id = r.json().get("id")
            check("в ответе нет пароля/хеша", "password" not in r.text and "hashed" not in r.text)
            check("повторная регистрация -> 409", c.post("/register", json={"email": email, "password": password}).status_code == 409)
            check("неверный пароль -> 401", c.post("/login", data={"username": email, "password": "nope-nope"}).status_code == 401)

            client_h = bearer(c, email, password)
            admin_h = bearer(c, admin_email, admin_password)
            check("вход клиента и админа выдаёт токены", "Bearer " in client_h["Authorization"] and len(admin_h["Authorization"]) > 20)

            # --- JWT и роли ---
            check("без токена -> 401", c.get("/users/me").status_code == 401)
            check("мусорный токен -> 401", c.get("/users/me", headers={"Authorization": "Bearer abc"}).status_code == 401)
            check("GET /users/me", c.get("/users/me", headers=client_h).json().get("email") == email)
            check("GET /users клиенту -> 403", c.get("/users", headers=client_h).status_code == 403)
            check("GET /users админу -> 200", c.get("/users", headers=admin_h).status_code == 200)

            # --- датасеты ---
            r = c.post("/datasets", headers=client_h, data={"name": "Live"}, files={"file": ("data.csv", CSV, "text/csv")})
            check("POST /datasets -> 201, row_count=3", r.status_code == 201 and r.json().get("row_count") == 3, r.text)
            ds_id = r.json().get("id")
            check("файл .exe отклонён -> 400", c.post("/datasets", headers=client_h, data={"name": "x"}, files={"file": ("a.exe", b"zz", "x/y")}).status_code == 400)
            check("загрузка от админа -> 403", c.post("/datasets", headers=admin_h, data={"name": "x"}, files={"file": ("data.csv", CSV, "text/csv")}).status_code == 403)
            check("GET /datasets/{id}", c.get(f"/datasets/{ds_id}", headers=client_h).status_code == 200)
            check("админ видит чужой датасет", c.get(f"/datasets/{ds_id}", headers=admin_h).status_code == 200)
            check("админ не может менять чужой -> 404", c.put(f"/datasets/{ds_id}", headers=admin_h, json={"name": "x"}).status_code == 404)
            check("PUT /datasets/{id}", c.put(f"/datasets/{ds_id}", headers=client_h, json={"name": "Renamed"}).json().get("name") == "Renamed")
            check("GET /datasets (список клиента)", [d["id"] for d in c.get("/datasets", headers=client_h).json()] == [ds_id])

            # --- задачи (пайплайн создаём напрямую в БД, роутеры B не нужны) ---
            with SessionLocal() as db:
                algo = Algorithm(code=f"live-{suffix}", name="Live algo", grpc_handler="Handler", default_params={})
                db.add(algo)
                db.flush()
                pipeline = Pipeline(title="Live pipeline", is_published=True,
                                    steps=[PipelineStep(algorithm_id=algo.id, step_order=1, step_params={})])
                db.add(pipeline)
                db.commit()
                algo_id, pipeline_id = algo.id, pipeline.id

            r = c.post("/jobs", headers=client_h, json={"dataset_id": ds_id, "pipeline_id": pipeline_id})
            check("POST /jobs -> 201, статус PENDING", r.status_code == 201 and r.json().get("status") == "PENDING", r.text)
            job_id = r.json().get("id")
            check("результат не готов -> 409", c.get(f"/jobs/{job_id}/result", headers=client_h).status_code == 409)
            check("GET /jobs (мои задачи)", [j["id"] for j in c.get("/jobs", headers=client_h).json()] == [job_id])
            check("задача несуществующего датасета -> 404", c.post("/jobs", headers=client_h, json={"dataset_id": 999999, "pipeline_id": pipeline_id}).status_code == 404)

            with SessionLocal() as db:
                job = db.get(ProcessingJob, job_id)
                job.status, job.result_data = "COMPLETED", {"mean": 3.0}
                db.commit()
            r = c.get(f"/jobs/{job_id}/result", headers=client_h)
            check("результат готовой задачи -> 200", r.status_code == 200 and r.json().get("result") == {"mean": 3.0}, r.text)

            # --- целостность и удаление ---
            check("датасет с задачами нельзя удалить -> 409", c.delete(f"/datasets/{ds_id}", headers=client_h).status_code == 409)
            check("DELETE /jobs/{id} -> 204", c.delete(f"/jobs/{job_id}", headers=client_h).status_code == 204)
            check("DELETE /datasets/{id} -> 204", c.delete(f"/datasets/{ds_id}", headers=client_h).status_code == 204)
            check("файл удалён с диска", not any((UPLOAD_DIR / str(user_id)).glob("*.csv")) if (UPLOAD_DIR / str(user_id)).exists() else True)

            # --- смена роли ---
            check("PATCH роли -> ADMIN", c.patch(f"/users/{user_id}/role", headers=admin_h, json={"role": "ADMIN"}).json().get("role") == "ADMIN")
            check("права действуют сразу (тот же токен)", c.get("/users", headers=client_h).status_code == 200)
        finally:
            cleanup(user_id, pipeline_id, algo_id)
            print("\n(тестовые данные удалены)")

    print(f"\nИтог: {'ВСЁ ОК' if not failed else 'ЕСТЬ ОШИБКИ: ' + ', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
