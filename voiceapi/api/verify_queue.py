from __future__ import annotations

import datetime as dt

from django.core.cache import cache          # redis / memcached backend
from django.db import transaction
from django.utils import timezone

from .models.error_verify_phone_dialer import ErrorVerifyPhoneDialer
# (delay import to inside process_queue to avoid loop)

# ─────────────────────────────────────────────────────────────────────────────
#  Lock parameters
# ─────────────────────────────────────────────────────────────────────────────
LOCK_KEY   = "verify-queue-processing"
LOCK_TTL   = 25 * 60          # < beat interval (30 min) so we don't overlap
BATCH_SIZE = 100              # never hammer the remote with >100 pushes


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _acquire_lock() -> bool:
    """Return True iff we obtained the distributed mutex."""
    return cache.add(LOCK_KEY, "1", LOCK_TTL)     # atomic


def _release_lock() -> None:  # noqa: D401
    """Drop the mutex."""
    cache.delete(LOCK_KEY)


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC: call this from Celery task *or* management-command
# ─────────────────────────────────────────────────────────────────────────────
def process_queue() -> None:
    """
    Drain `api_error_verify_phone_dialer` oldest→newest.

    • Stops at first non-200 (to avoid loops while remote still rejects)
    • Deletes a row on success; bumps attempted_at on failure
    """
    if not _acquire_lock():
        print("verify-queue: another worker is active → skipping")
        return

    try:
        while True:
            rows = (
                ErrorVerifyPhoneDialer.objects
                .order_by("attempted_at")[:BATCH_SIZE]
            )
            if not rows:
                return

            for row in rows:
                payload = {
                    "ref_no":      row.ref_no,
                    "status":      row.status,
                    "retry_count": row.trials,
                    "retry_at":    timezone.now()
                                       .astimezone()
                                       .strftime("%Y-%m-%d %H:%M:%S"),
                }

                # late import avoids circular dependency
                from .call_status_pusher import CallStatusPusher
                ok = CallStatusPusher.push(payload)
                if not ok:
                    # failure → bump attempted_at so next run waits again
                    row.attempted_at = timezone.now()
                    row.save(update_fields=["attempted_at"])
                    return

                # delivered = 200 → delete row, continue
                row.delete()
    finally:
        _release_lock()
