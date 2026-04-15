from django.db import models

class CallDtmfStatus(models.Model):
    call_id = models.ForeignKey('PhoneDialer', on_delete=models.CASCADE, db_index=True)
    extension = models.IntegerField(default=0, db_index=True)
    dtmf_response = models.IntegerField(default=0, db_index=True)   

    class Meta:
        unique_together = (('call_id', 'extension'),)