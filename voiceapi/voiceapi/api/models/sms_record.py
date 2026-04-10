from django.db import models

class SmsRecord(models.Model):
    phone_number = models.CharField(max_length=10, db_index=True)
    sms_sent = models.TextField()
    datetime = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'api_sms_record'