from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from src.api.routers import auth
from src.api.routers import users
from src.api.routers import datasets
from src.api.routers import jobs

app = FastAPI(
    title="Cloud Data Pipeline & Analytics Platform",
    version="0.2.0",
    description="REST API (лабораторная работа №2)",
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(datasets.router)
app.include_router(jobs.router)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": "Database constraint violated"})


@app.get("/health", tags=["service"])
def health():
    return {"status": "ok"}