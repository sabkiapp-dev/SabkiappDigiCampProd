from celery import shared_task
from .verify_queue import process_queue


@shared_task(name="api.process_verify_queue")
def process_verify_queue_task() -> None:
    """
    Celery wrapper around `verify_queue.process_queue()`.
    Triggered by beat every 30 min *or* manually via `.delay()`.
    """
    process_queue()
