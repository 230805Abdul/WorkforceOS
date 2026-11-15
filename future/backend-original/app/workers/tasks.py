import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="send_application_status_email", bind=True, max_retries=3, default_retry_delay=30)
def send_application_status_email(self, candidate_email: str, job_title: str, new_status: str) -> dict:
    """Example async job: notify a candidate their application status changed.
    Kept outside the request/response cycle so the API stays fast under load."""
    try:
        logger.info("Sending status email to %s for job '%s' -> %s", candidate_email, job_title, new_status)
        # Real implementation: call an email provider (SES/SendGrid) here.
        return {"sent": True, "to": candidate_email}
    except Exception as exc:  # pragma: no cover - illustrative retry path
        raise self.retry(exc=exc) from exc


@celery_app.task(name="score_resume_match")
def score_resume_match(application_id: str, resume_text: str, job_description: str) -> dict:
    """Stub for an AI matching service call (e.g. an LLM scoring prompt-response
    pair). Swapped for a real model/API call in production."""
    logger.info("Scoring application %s", application_id)
    return {"application_id": application_id, "score": 0.0, "status": "stubbed"}
