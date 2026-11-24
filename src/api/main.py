import logging

import grpc
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from src.api.grpc_client import grpc_error_to_http, rpc_code, rpc_details
from src.api.routers import auth
from src.api.routers import users
from src.api.routers import datasets
from src.api.routers import jobs, admin, algorithms, pipelines

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("api.main")

app = FastAPI(
    title="Cloud Data Pipeline & Analytics Platform",
    version="0.3.0",
    description="REST API + gRPC-клиент (лабораторная работа №3)",
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(datasets.router)
app.include_router(jobs.router)
app.include_router(algorithms.router)
app.include_router(pipelines.router)
app.include_router(admin.router)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": "Database constraint violated"})


@app.exception_handler(grpc.RpcError)
async def grpc_error_handler(request: Request, exc: grpc.RpcError):
    """INVALID_ARGUMENT->400, UNAVAILABLE->503, DEADLINE_EXCEEDED->504, остальное->502."""
    http_status, detail = grpc_error_to_http(exc)
    logger.warning(
        "gRPC error on %s %s: code=%s, details=%s -> HTTP %s",
        request.method, request.url.path, rpc_code(exc), rpc_details(exc), http_status,
    )
    return JSONResponse(status_code=http_status, content={"detail": detail})


@app.get("/health", tags=["service"])
def health():
    return {"status": "ok"}