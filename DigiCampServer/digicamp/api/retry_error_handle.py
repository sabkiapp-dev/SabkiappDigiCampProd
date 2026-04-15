"""
retry_error_handle.py
=====================
Robust, single-process retry handler for ErrorVerifyPhoneDialer.
"""

from __future__ import annotations

import os, random, time
from typing import Optional

from django.core.cache import cache
from django.utils import timezone

try:
    # Package-relative import (when executed via `python -m digicamp_server.api.retry_error_handle`)
    from .models.error_verify_phone_dialer import ErrorVerifyPhoneDialer
except ImportError:  # Stand-alone execution fallback
    import os, sys
    from pathlib import Path

    # Ensure project root is on sys.path so that `digicamp_server.settings` and `models` are importable
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Configure Django settings for standalone execution
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "digicamp_server.settings")
    try:
        import django
        django.setup()
    except Exception as exc:
        # If django.setup() fails we still attempt the import; model import will raise clearer error
        print(f"Warning: django.setup() failed – {exc}")

    from api.models.error_verify_phone_dialer import ErrorVerifyPhoneDialer

# ── locking constants ───────────────────────────────────────────────
LOCK_KEY        = "verify-queue-processing"
LOCK_TTL        = 15 * 60        # 15 minutes
SELF_CHECK_LAT  = 0.10           # 100 ms to verify ownership
BATCH_SIZE      = 100            # DB rows per loop


# ── lock helpers ────────────────────────────────────────────────────
def _now_ns() -> int:
    return time.time_ns()


def _make_stamp() -> str:
    return f"{_now_ns()}-{random.randint(100_000, 999_999)}"


def _is_stale(stamp: str) -> bool:
    try:
        created_ns = int(stamp.split("-")[0])
        return (_now_ns() - created_ns) / 1_000_000_000 > LOCK_TTL
    except Exception:
        return True


def _acquire_lock() -> Optional[str]:
    stamp = _make_stamp()

    if cache.add(LOCK_KEY, stamp, LOCK_TTL):
        time.sleep(SELF_CHECK_LAT)
        if cache.get(LOCK_KEY) == stamp:
            print(f"• LOCK ACQUIRED ({stamp})")
            return stamp
        print("• Lost race after initial acquire")
        return None

    current = cache.get(LOCK_KEY)
    if current and not _is_stale(current):
        print("• Another worker holds the lock – skipping")
        return None

    print("• Stale/corrupt lock detected – force releasing")
    cache.delete(LOCK_KEY)
    if cache.add(LOCK_KEY, stamp, LOCK_TTL):
        time.sleep(SELF_CHECK_LAT)
        if cache.get(LOCK_KEY) == stamp:
            print(f"• LOCK RE-ACQUIRED ({stamp})")
            return stamp
    print("• Failed to acquire lock after cleanup")
    return None


def _release_lock(stamp: Optional[str]) -> None:
    if stamp and cache.get(LOCK_KEY) == stamp:
        cache.delete(LOCK_KEY)
        print(f"• LOCK RELEASED ({stamp})")


# ── retry processor ────────────────────────────────────────────────
def process_retry_queue() -> None:
    """
    Iterate rows in ErrorVerifyPhoneDialer ordered by *id* (oldest first):

    • On HTTP 200 → delete row and move on.  
    • On any failure / non-200 / exception → save updated `trials`
      and stop (remaining rows will be retried in the next run).
    """
    stamp = _acquire_lock()
    if not stamp:
        return

    # Optional delay to test locking across multiple processes
    delay_secs = int(os.getenv("RETRY_HANDLER_SLEEP", "0"))
    if delay_secs > 0:
        print(f"• Sleeping {delay_secs}s to hold lock for testing …")
        time.sleep(delay_secs)

    try:
        if not ErrorVerifyPhoneDialer.objects.exists():
            print("• No rows in ErrorVerifyPhoneDialer – nothing to do")
            return

        processed = 0
        try:
            from .sabkiapp_client import send_verify_status
        except ImportError:
            from api.sabkiapp_client import send_verify_status

        while True:
            rows = (
                ErrorVerifyPhoneDialer.objects
                .all()
                .order_by("id")[:BATCH_SIZE]
            )
            if not rows:
                break

            for row in rows:
                if cache.get(LOCK_KEY) != stamp:  # lost the lock
                    print("• Lost lock mid-run – aborting")
                    return

                print(f"• Retrying {row.ref_no} (attempt {row.trials})")

                payload = {
                    "ref_no":      row.ref_no,
                    "status":      row.status,
                    "retry_count": row.trials,
                    "retry_at":    row.attempted_at.strftime("%Y-%m-%d %H:%M:%S") if row.attempted_at else None,
                }

                try:
                    ok, code, body = send_verify_status(payload)
                except Exception as exc:
                    print(f"× Exception while pushing {row.ref_no}: {exc}")
                    ok = False

                if ok:
                    row.delete()
                    processed += 1
                    print(f"✓ Success – deleted {row.ref_no}")
                else:
                    row.save(update_fields=["trials", "attempted_at"])
                    print(f"× Still failing – saved {row.ref_no} and exiting")
                    return

        print(f"• Retry handler completed – total successes: {processed}")

    finally:
        _release_lock(stamp)



if __name__ == "__main__":
    process_retry_queue()