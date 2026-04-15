from django.db import models
from django.db.models import Func
import datetime
import pytz

# --- helper that strips tzinfo -------------------------------------------
IST = pytz.timezone('Asia/Kolkata')

def now_ist():
    """
    Return current time in Asia/Kolkata **without** timezone info,
    so it can be stored when USE_TZ = False.
    """
    return datetime.datetime.now(IST).replace(tzinfo=None)

class CurrentTimestamp(Func):
    template = 'CURRENT_TIMESTAMP'

'''
Sent status 
0 - Not sent
1 - In progress
2 - Unanswered
3 - Ongoing Call
4 - cancelled
5 - Completed
'''


class PhoneDialer(models.Model):
    phone_number = models.CharField(max_length=10, db_index=True)
    user = models.ForeignKey('Users', on_delete=models.CASCADE, db_index=True)
    campaign = models.ForeignKey('Campaign', on_delete=models.CASCADE, db_index=True)
    sent_status = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    name = models.CharField(max_length=255, db_index=True, null=True, blank=True, default=None)
    sent_datetime = models.DateTimeField(null=True, blank=True, db_index=True)
    # ── manually added columns ───────────────────────────────
    ref_no = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    channel_name = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    surveyor_name = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    gender = models.CharField(max_length=10, null=True, blank=True, db_index=True)
    trials = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    call_through = models.CharField(max_length=10, db_index=True, default=None, null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    created_at      = models.DateTimeField(default=now_ist,    db_index=True)
    updated_at      = models.DateTimeField(default=now_ist,    db_index=True)
    block_trials = models.IntegerField(null=True, blank=True, default=0, db_index=True)

    def save(self, *args, **kwargs):
        # Always stamp updated_at in IST
        self.updated_at = now_ist()
        # On first save, set created_at as well
        if not self.pk:
            self.created_at = now_ist()
        return super().save(*args, **kwargs)

    class Meta:
        db_table = 'api_phone_dialer'