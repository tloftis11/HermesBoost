import ssl

from celery import Celery

from app.config import settings

celery_app = Celery(
    "hermesboost",
    broker=settings.UPSTASH_REDIS_URL,
    backend=settings.UPSTASH_REDIS_URL,
)
celery_app.conf.task_always_eager = settings.CELERY_TASK_ALWAYS_EAGER
celery_app.conf.task_acks_late = True

if settings.UPSTASH_REDIS_URL.startswith("rediss://"):
    # Celery's redis broker/backend -- unlike the plain redis-py client -- does
    # not default ssl_cert_reqs for TLS (rediss://) URLs and raises on startup
    # without it. Upstash presents a valid public cert, so verify it properly
    # rather than disabling verification.
    tls_opts = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    celery_app.conf.broker_use_ssl = tls_opts
    celery_app.conf.redis_backend_use_ssl = tls_opts

# Import task modules so they register with the app.
from app.tasks import profile_dataset, score_model, train_model  # noqa: E402,F401
