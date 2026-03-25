from __future__ import annotations

from celery import Celery

from server.config.settings import settings

celery_app = Celery(
    "rpml_backend",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_serializer=["json"],
    result_serializer="json",
    timezone="UTC",
    task_track_started=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
)

import server.infrastructure.queue.tasks  # noqa: E402,F401  # register tasks
