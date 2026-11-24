"""Тесты ЛР3: POST /pipelines/{id}/validate, POST /jobs/{id}/run и маппинг ошибок gRPC -> HTTP."""
import grpc
import pytest

from src.api.grpc_client import grpc_error_to_http


class FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode, details: str = ""):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


class FailingClient:
    """Подмена gRPC-клиента: любой вызов падает с заданным кодом."""

    def __init__(self, code: grpc.StatusCode, details: str = ""):
        self._error = FakeRpcError(code, details)

    def execute_pipeline(self, job, dataset, pipeline):
        raise self._error

    def validate_pipeline(self, pipeline):
        raise self._error


# ------------------------------------------------------------ маппинг (unit)


@pytest.mark.parametrize(
    "code, expected_status",
    [
        (grpc.StatusCode.INVALID_ARGUMENT, 400),
        (grpc.StatusCode.UNAVAILABLE, 503),
        (grpc.StatusCode.DEADLINE_EXCEEDED, 504),
        (grpc.StatusCode.INTERNAL, 502),
        (grpc.StatusCode.UNKNOWN, 502),
    ],
)
def test_grpc_error_to_http(code, expected_status):
    status_code, detail = grpc_error_to_http(FakeRpcError(code, "boom"))
    assert status_code == expected_status
    assert detail


def test_invalid_argument_passes_details():
    _, detail = grpc_error_to_http(FakeRpcError(grpc.StatusCode.INVALID_ARGUMENT, "Pipeline must contain at least one step"))
    assert detail == "Pipeline must contain at least one step"


# ------------------------------------------------------------ POST /pipelines/{id}/validate


def test_validate_ok(client, user, make_pipeline):
    pipeline = make_pipeline(user.id, steps=2)
    r = client.post(f"/pipelines/{pipeline.id}/validate", headers=user.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pipeline_id"] == pipeline.id
    assert body["is_valid"] is True
    assert body["errors"] == []
    assert len(body["supported_handlers"]) > 0


def test_validate_empty_pipeline_is_invalid(client, user, make_pipeline):
    pipeline = make_pipeline(user.id, steps=0)
    r = client.post(f"/pipelines/{pipeline.id}/validate", headers=user.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_valid"] is False
    assert body["errors"]


def test_validate_not_found(client, user):
    r = client.post("/pipelines/999999/validate", headers=user.headers)
    assert r.status_code == 404


def test_validate_foreign_unpublished_pipeline_hidden(client, user, other_user, make_pipeline):
    pipeline = make_pipeline(user.id, published=False)
    r = client.post(f"/pipelines/{pipeline.id}/validate", headers=other_user.headers)
    assert r.status_code == 404


def test_validate_published_pipeline_visible_to_others(client, user, other_user, make_pipeline):
    pipeline = make_pipeline(user.id, published=True)
    r = client.post(f"/pipelines/{pipeline.id}/validate", headers=other_user.headers)
    assert r.status_code == 200


def test_validate_requires_auth(client, user, make_pipeline):
    pipeline = make_pipeline(user.id)
    assert client.post(f"/pipelines/{pipeline.id}/validate").status_code == 401


def test_validate_grpc_unavailable_returns_503(client, user, make_pipeline, dead_grpc_client, use_grpc_client):
    """Реальный клиент к порту без сервера -> UNAVAILABLE -> 503."""
    pipeline = make_pipeline(user.id)
    use_grpc_client(dead_grpc_client)
    r = client.post(f"/pipelines/{pipeline.id}/validate", headers=user.headers)
    assert r.status_code == 503


def test_validate_grpc_timeout_returns_504(client, user, make_pipeline, use_grpc_client):
    pipeline = make_pipeline(user.id)
    use_grpc_client(FailingClient(grpc.StatusCode.DEADLINE_EXCEEDED))
    r = client.post(f"/pipelines/{pipeline.id}/validate", headers=user.headers)
    assert r.status_code == 504


# ------------------------------------------------------------ POST /jobs/{id}/run


def test_run_job_success(client, user, make_job):
    job, dataset, _ = make_job(user.id, steps=2)

    r = client.post(f"/jobs/{job.id}/run", headers=user.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == job.id
    assert body["status"] == "COMPLETED"
    assert body["current_step"] == 2
    assert body["finished_at"] is not None

    # существующий GET /jobs/{id}/result теперь отдаёт вычисленный результат
    res = client.get(f"/jobs/{job.id}/result", headers=user.headers)
    assert res.status_code == 200, res.text
    result = res.json()["result"]
    assert result["dataset_id"] == dataset.id
    assert result["initial_rows"] == dataset.row_count
    assert len(result["steps_summary"]) == 2


def test_result_before_run_is_conflict(client, user, make_job):
    job, _, _ = make_job(user.id)
    assert client.get(f"/jobs/{job.id}/result", headers=user.headers).status_code == 409


def test_run_job_twice_is_conflict(client, user, make_job):
    job, _, _ = make_job(user.id)
    assert client.post(f"/jobs/{job.id}/run", headers=user.headers).status_code == 200
    assert client.post(f"/jobs/{job.id}/run", headers=user.headers).status_code == 409


def test_run_job_not_found(client, user):
    assert client.post("/jobs/999999/run", headers=user.headers).status_code == 404


def test_run_foreign_job_is_404(client, user, other_user, make_job):
    job, _, _ = make_job(user.id)
    assert client.post(f"/jobs/{job.id}/run", headers=other_user.headers).status_code == 404


def test_run_requires_auth(client, user, make_job):
    job, _, _ = make_job(user.id)
    assert client.post(f"/jobs/{job.id}/run").status_code == 401


def test_run_empty_pipeline_maps_invalid_argument_to_400(client, user, make_job):
    """Реальный сервер отвечает INVALID_ARGUMENT на конвейер без шагов -> 400, задача FAILED."""
    job, _, _ = make_job(user.id, steps=0)
    r = client.post(f"/jobs/{job.id}/run", headers=user.headers)
    assert r.status_code == 400
    assert "at least one step" in r.json()["detail"]
    assert client.get(f"/jobs/{job.id}", headers=user.headers).json()["status"] == "FAILED"


def test_run_grpc_unavailable_returns_503_and_job_stays_pending(client, user, make_job, dead_grpc_client, use_grpc_client):
    """gRPC-сервис не запущен -> 503, а задачу можно запустить повторно (остаётся PENDING)."""
    job, _, _ = make_job(user.id)
    use_grpc_client(dead_grpc_client)

    r = client.post(f"/jobs/{job.id}/run", headers=user.headers)
    assert r.status_code == 503
    assert client.get(f"/jobs/{job.id}", headers=user.headers).json()["status"] == "PENDING"


@pytest.mark.parametrize(
    "code, expected_http, expected_job_status",
    [
        (grpc.StatusCode.INVALID_ARGUMENT, 400, "FAILED"),
        (grpc.StatusCode.UNAVAILABLE, 503, "PENDING"),
        (grpc.StatusCode.DEADLINE_EXCEEDED, 504, "FAILED"),
        (grpc.StatusCode.INTERNAL, 502, "FAILED"),
    ],
)
def test_run_grpc_error_mapping(client, user, make_job, use_grpc_client, code, expected_http, expected_job_status):
    job, _, _ = make_job(user.id)
    use_grpc_client(FailingClient(code, "simulated failure"))

    r = client.post(f"/jobs/{job.id}/run", headers=user.headers)
    assert r.status_code == expected_http
    assert client.get(f"/jobs/{job.id}", headers=user.headers).json()["status"] == expected_job_status