from __future__ import annotations

from server.application.use_cases.run_optimization_async import run_optimization_job_for_task_id
from server.infrastructure.queue.celery_app import celery_app


@celery_app.task(name="optimization.run_optimization", bind=True)
def run_optimization_task(self) -> None:
    run_optimization_job_for_task_id(self.request.id)
