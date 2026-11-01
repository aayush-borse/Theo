"""Optional durable distributed queue. Run with: celery -A app.workers.celery_app.celery_app worker -l INFO"""
import os
from celery import Celery
celery_app=Celery("theo",include=["app.workers.tasks"],broker=os.getenv("THEO_REDIS_URL","redis://localhost:6379/0"),backend=os.getenv("THEO_REDIS_URL","redis://localhost:6379/0"))
celery_app.conf.update(task_serializer="json",accept_content=["json"],result_serializer="json",timezone="UTC",enable_utc=True,task_acks_late=True,worker_prefetch_multiplier=1,task_track_started=True,broker_connection_retry_on_startup=True)
