from django.db import models

class CallInfo(models.Model):
    id = models.AutoField(primary_key=True, db_index=True)
    phone_number = models.BigIntegerField(null=True, blank=True, default=0, db_index=True)
    campaign_id = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    host = models.CharField(max_length=255, null=True, blank=True, default='', db_index=True)
    port = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    datetime = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.IntegerField(null=True, blank=True, default=0, db_index=True)