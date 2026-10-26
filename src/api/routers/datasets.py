import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, status

from src.api.crud_modules import dataset_crud, extra_a
from src.api.dependencies import ClientUser, CurrentUser, DbSession
from src.api.schemas.dataset import DatasetOut, DatasetUpdate
from src.api.settings import ALLOWED_EXTENSIONS, MAX_UPLOAD_MB, ROLE_ADMIN, UPLOAD_DIR
from src.models.user import User

router = APIRouter(prefix="/datasets", tags=["datasets"])

CHUNK = 1024 * 1024

def _get_dataset_or_404(db, dataset_id: int, user: User, *, owner_only: bool = False):
    dataset = dataset_crud.get_dataset_by_id(db, dataset_id)
    allowed = dataset is not None and (
        dataset.user_id == user.id or (user.role == ROLE_ADMIN and not owner_only)
    )
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
    return dataset


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
def upload_dataset(
    user: ClientUser,
    db: DbSession,
    name: Annotated[str, Form(min_length=1, max_length=255)],
    file: UploadFile,
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Allowed file types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    user_dir = UPLOAD_DIR / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    stored_path = user_dir / f"{uuid.uuid4().hex}{ext}"
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024

    size = 0
    newlines = 0
    last_byte = b""
    try:
        with open(stored_path, "wb") as out:
            while chunk := file.file.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File is larger than {MAX_UPLOAD_MB} MB"
                    )
                newlines += chunk.count(b"\n")
                last_byte = chunk[-1:]
                out.write(chunk)
        if size == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is empty")

        lines = newlines + (0 if last_byte == b"\n" else 1)
        row_count = max(lines - 1, 0)
        return dataset_crud.create_dataset(db, user.id, name, str(stored_path), row_count, size)
    except BaseException:
        stored_path.unlink(missing_ok=True)
        raise


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    user: CurrentUser,
    db: DbSession,
    user_id: int | None = Query(None, description="Только для ADMIN: фильтр по владельцу"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    owner_filter = user_id if user.role == ROLE_ADMIN else user.id
    return extra_a.get_datasets(db, owner_filter, skip, limit)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: int, user: CurrentUser, db: DbSession):
    return _get_dataset_or_404(db, dataset_id, user)


@router.put("/{dataset_id}", response_model=DatasetOut)
def update_dataset(dataset_id: int, data: DatasetUpdate, user: CurrentUser, db: DbSession):
    dataset = _get_dataset_or_404(db, dataset_id, user, owner_only=True)
    return dataset_crud.update_dataset(db, dataset.id, name=data.name)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: int, user: CurrentUser, db: DbSession):
    dataset = _get_dataset_or_404(db, dataset_id, user, owner_only=True)
    if extra_a.count_jobs_for_dataset(db, dataset.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dataset has processing jobs and cannot be deleted")
    file_path = Path(dataset.file_path)
    dataset_crud.delete_dataset(db, dataset.id)
    file_path.unlink(missing_ok=True)