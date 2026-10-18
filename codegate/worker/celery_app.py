import os

from celery import Celery
from dynaconf import Dynaconf

# Attempt to load settings just to see if we can derive broker URL if not explicitly set
try:
    from pr_agent.config_loader import get_settings
    redis_url = get_settings().get("CELERY_BROKER_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
except Exception:
    redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

# Ensure Dynaconf environment variables are loaded appropriately
os.environ.setdefault("FORCELOAD", "true")

celery_app = Celery(
    "codegate_worker",
    broker=redis_url,
    backend=redis_url,
    include=["codegate.worker.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour absolute limit
    worker_prefetch_multiplier=1, # process one at a time per worker process
)
