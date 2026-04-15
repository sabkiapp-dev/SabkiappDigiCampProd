from django.db import models
from ..models.users import Users
from ..models.sms_template import SmsTemplate
from datetime import date


class SmsCampaign(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    priority = models.IntegerField(db_index=True)
    start_time = models.TimeField(db_index=True)
    end_time = models.TimeField(db_index=True)
    template = models.ForeignKey(SmsTemplate, on_delete=models.CASCADE, db_index=True, null=True, blank=True)
    status = models.IntegerField(null=True, blank=True, default=1, db_index=True)
    user = models.ForeignKey(Users, on_delete=models.CASCADE, db_index=True)
    contact_count = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    start_date = models.DateField(default=date(2024, 1, 1), db_index=True)
    end_date = models.DateField(default=date(2050, 12, 31), db_index=True)
    class Meta:
        unique_together = ('user', 'name',)