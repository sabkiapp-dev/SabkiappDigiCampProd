from django.db import models
from django.core.validators import RegexValidator
from .user_hosts import UserHosts

class CallStatus(models.Model):
    phone = models.CharField(max_length=10, validators=[RegexValidator(r'^\d{10}$')], db_index=True)
    campaign = models.ForeignKey('Campaign', on_delete=models.CASCADE, db_index=True)
    port = models.IntegerField(db_index=True)
    host = models.ForeignKey(UserHosts, on_delete=models.CASCADE)
    start_time = models.DateTimeField(null=True, blank=True, db_index=True)
    end_time = models.DateTimeField(null=True, blank=True, db_index=True)
    duration = models.IntegerField(default=0, db_index=True)
    dial = models.OneToOneField('PhoneDialer', on_delete=models.CASCADE)