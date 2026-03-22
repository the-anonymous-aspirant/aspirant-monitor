"""In-process scheduler for periodic tasks."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import DAILY_REPORT_HOUR, email_enabled

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def setup_scheduler():
    """Register scheduled tasks and start the scheduler."""
    if not email_enabled():
        logger.info("Email not configured — daily report scheduler disabled.")
        return

    # Import here to avoid circular imports
    from app.daily_report import send_daily_report

    scheduler.add_job(
        send_daily_report,
        trigger=CronTrigger(hour=DAILY_REPORT_HOUR, timezone="Europe/Berlin"),
        id="daily_report",
        name="Daily health report",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started. Daily report at %02d:00 CET.", DAILY_REPORT_HOUR)


def shutdown_scheduler():
    """Stop the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


def get_scheduler_status() -> dict:
    """Return scheduler state for the /report/status endpoint."""
    if not scheduler.running:
        return {"enabled": False, "reason": "email not configured" if not email_enabled() else "scheduler not running"}

    job = scheduler.get_job("daily_report")
    if not job:
        return {"enabled": False, "reason": "no daily report job"}

    next_run = job.next_run_time
    return {
        "enabled": True,
        "next_report": next_run.isoformat() if next_run else None,
        "report_hour_cet": DAILY_REPORT_HOUR,
    }
