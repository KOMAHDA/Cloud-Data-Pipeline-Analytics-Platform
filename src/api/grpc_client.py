"""gRPC-клиент для AnalyticsService (FastAPI -> gRPC-сервис)."""
import json
import logging
import time
from typing import Any

import grpc
from fastapi import status

from src.config import GRPC_HOST, GRPC_PORT
from src.grpc_generated import analytics_pb2, analytics_pb2_grpc

logger = logging.getLogger("api.grpc_client")

DEFAULT_TIMEOUT = 10.0


# === Вспомогательные функции для работы с grpc.RpcError ===


def rpc_code(exc: grpc.RpcError) -> grpc.StatusCode | None:
    """Код ошибки gRPC (у базового RpcError метода code() может не быть)."""
    code = getattr(exc, "code", None)
    return code() if callable(code) else None


def rpc_details(exc: grpc.RpcError) -> str:
    details = getattr(exc, "details", None)
    return (details() if callable(details) else "") or ""


def grpc_error_to_http(exc: grpc.RpcError) -> tuple[int, str]:
    """Маппинг gRPC-ошибки в (HTTP-статус, текст detail)."""
    code = rpc_code(exc)
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return status.HTTP_400_BAD_REQUEST, rpc_details(exc) or "Invalid argument"
    if code == grpc.StatusCode.UNAVAILABLE:
        return status.HTTP_503_SERVICE_UNAVAILABLE, "gRPC analytics service is unavailable"
    if code == grpc.StatusCode.DEADLINE_EXCEEDED:
        return status.HTTP_504_GATEWAY_TIMEOUT, "gRPC analytics service timed out"
    name = code.name if code is not None else "UNKNOWN"
    return status.HTTP_502_BAD_GATEWAY, f"gRPC analytics service error: {name}"


def _parse_json(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Cannot parse JSON from gRPC response: %r", raw[:200])
        return None


# === Клиент ===


class AnalyticsGrpcClient:
    """Обёртка над AnalyticsServiceStub.

    Канал в gRPC создаётся лениво, поэтому клиент можно создавать,
    даже если gRPC-сервер ещё не запущен: ошибка (UNAVAILABLE) появится
    только при вызове метода.
    """

    def __init__(self, host: str = GRPC_HOST, port: int = GRPC_PORT, timeout: float = DEFAULT_TIMEOUT):
        self.target = f"{host}:{port}"
        self.timeout = timeout
        self._channel = grpc.insecure_channel(self.target)
        self._stub = analytics_pb2_grpc.AnalyticsServiceStub(self._channel)

    def close(self) -> None:
        self._channel.close()

    @staticmethod
    def _build_steps(steps) -> list[analytics_pb2.PipelineStepInput]:
        return [
            analytics_pb2.PipelineStepInput(
                step_order=step.step_order,
                algorithm_code=step.algorithm.code,
                grpc_handler=step.algorithm.grpc_handler,
                params_json=json.dumps(step.step_params or {}, ensure_ascii=False),
            )
            for step in steps
        ]

    def execute_pipeline(self, job, dataset, pipeline) -> dict[str, Any]:
        """Запускает конвейер на gRPC-сервисе и возвращает разобранный ответ."""
        request = analytics_pb2.ExecutePipelineRequest(
            job_id=job.id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            file_path=dataset.file_path,
            row_count=dataset.row_count,
            steps=self._build_steps(pipeline.steps),
        )
        logger.info(
            "[FastAPI -> gRPC] ExecutePipeline -> %s: job_id=%s, dataset='%s' (%s rows), steps=%s, timeout=%ss",
            self.target, job.id, dataset.name, dataset.row_count, len(request.steps), self.timeout,
        )
        started = time.perf_counter()
        try:
            response = self._stub.ExecutePipeline(request, timeout=self.timeout)
        except grpc.RpcError as exc:
            logger.error(
                "[FastAPI <- gRPC] ExecutePipeline FAILED: job_id=%s, code=%s, details=%s (%.0f ms)",
                job.id, rpc_code(exc), rpc_details(exc), (time.perf_counter() - started) * 1000,
            )
            raise
        logger.info(
            "[FastAPI <- gRPC] ExecutePipeline OK: job_id=%s, status=%s, completed_steps=%s (%.0f ms)",
            job.id, response.status, response.completed_steps, (time.perf_counter() - started) * 1000,
        )
        return {
            "job_id": response.job_id,
            "status": response.status,
            "completed_steps": response.completed_steps,
            "result": _parse_json(response.result_json),
            "error_message": response.error_message or None,
            "step_results": [
                {
                    "step_order": sr.step_order,
                    "algorithm_code": sr.algorithm_code,
                    "status": sr.status,
                    "duration_ms": sr.duration_ms,
                    "metrics": _parse_json(sr.metrics_json),
                }
                for sr in response.step_results
            ],
        }

    def validate_pipeline(self, pipeline) -> dict[str, Any]:
        """Проверяет конвейер на gRPC-сервисе."""
        request = analytics_pb2.ValidatePipelineRequest(steps=self._build_steps(pipeline.steps))
        logger.info(
            "[FastAPI -> gRPC] ValidatePipeline -> %s: pipeline_id=%s, steps=%s, timeout=%ss",
            self.target, pipeline.id, len(request.steps), self.timeout,
        )
        started = time.perf_counter()
        try:
            response = self._stub.ValidatePipeline(request, timeout=self.timeout)
        except grpc.RpcError as exc:
            logger.error(
                "[FastAPI <- gRPC] ValidatePipeline FAILED: pipeline_id=%s, code=%s, details=%s (%.0f ms)",
                pipeline.id, rpc_code(exc), rpc_details(exc), (time.perf_counter() - started) * 1000,
            )
            raise
        logger.info(
            "[FastAPI <- gRPC] ValidatePipeline OK: pipeline_id=%s, is_valid=%s, errors=%s (%.0f ms)",
            pipeline.id, response.is_valid, len(response.errors), (time.perf_counter() - started) * 1000,
        )
        return {
            "is_valid": response.is_valid,
            "errors": list(response.errors),
            "supported_handlers": list(response.supported_handlers),
        }