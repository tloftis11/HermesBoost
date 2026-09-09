from celery import Celery

from app.config import settings

celery_app = Celery(
    "hermesboost",
    broker=settings.UPSTASH_REDIS_URL,
    backend=settings.UPSTASH_REDIS_URL,
)
celery_app.conf.task_always_eager = settings.CELERY_TASK_ALWAYS_EAGER
celery_app.conf.task_acks_late = True

# Import task modules so they register with the app.
from app.tasks import profile_dataset  # noqa: E402,F401
