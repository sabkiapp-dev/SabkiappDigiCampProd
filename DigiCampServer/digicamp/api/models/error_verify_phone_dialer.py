import datetime
import pytz
from django.db import models

# ── helper to stamp IST without tz-info ────────────────────────────────────
IST = pytz.timezone("Asia/Kolkata")

def now_ist_naive():
    """Return current Asia/Kolkata time *without* tzinfo (USE_TZ = False)."""
    return datetime.datetime.now(IST).replace(tzinfo=None)


class ErrorVerifyPhoneDialer(models.Model):
    """
    Stores every call-status push that did **not** receive HTTP 200
    from the client.
    """

    STATUS_CHOICES = [
        ("no_answer", "No Answer"),
        ("no_dtmf", "No DTMF"),
        ("rejected", "Rejected"),
        ("accepted", "Accepted"),
    ]

    ref_no         = models.CharField(max_length=255, db_index=True)
    trials         = models.IntegerField(db_index=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, db_index=True)

    # When we tried to notify
    attempted_at   = models.DateTimeField(default=now_ist_naive, db_index=True)
    # What the remote server replied
    response_code  = models.IntegerField(null=True, blank=True)
    response_body  = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "api_error_verify_phone_dialer"
        indexes = [
            models.Index(fields=["ref_no"]),
            models.Index(fields=["trials"]),
            models.Index(fields=["status"]),
            models.Index(fields=["attempted_at"]),
        ]

    def __str__(self):
        return f"{self.ref_no} → {self.status} ({self.response_code})"
