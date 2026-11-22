import multiprocessing
import os

# Класс воркера: Uvicorn для поддержки async FastAPI
worker_class = "uvicorn.workers.UvicornWorker"

# Число воркеров: из переменной окружения или формула 2 * ядра + 1, но не больше 4
WEB_CONCURRENCY = os.getenv("WEB_CONCURRENCY")
if WEB_CONCURRENCY:
    workers = int(WEB_CONCURRENCY)
else:
    workers = min(2 * multiprocessing.cpu_count() + 1, 4)

# Таймаут: если воркер не отвечает 60 секунд, перезапускается
timeout = 60

# Логи в консоль (stdout/stderr)
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Имя приложения
bind = "0.0.0.0:8000"