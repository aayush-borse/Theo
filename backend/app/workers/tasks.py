from .celery_app import celery_app

@celery_app.task(name="theo.annotate_dataset",bind=True,max_retries=3,default_retry_delay=10)
def annotate_dataset_task(self, job_id: str):
    # Import lazily so workers share the same application service and DB configuration.
    from app.main import _run_annotation_job
    try:
        _run_annotation_job(job_id)
        from app.core.database import SessionLocal
        from app.domain.models import ProcessingJob
        db=SessionLocal()
        try:
            job=db.get(ProcessingJob,job_id)
            if job and job.status=="FAILED": raise RuntimeError(job.error or "Annotation job failed")
        finally: db.close()
    except Exception as exc:
        raise self.retry(exc=exc)
