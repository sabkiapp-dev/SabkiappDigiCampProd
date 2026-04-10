from django.db import models
from django.conf import settings
from .misscall_management import MisscallManagement

class Misscalls(models.Model):
    phone_number = models.CharField(max_length=10, db_index=True)
    datetime = models.DateTimeField(db_index=True)
    misscall_management = models.ForeignKey(MisscallManagement, on_delete=models.CASCADE, db_index=True)
    campaign = models.ForeignKey('Campaign', on_delete=models.CASCADE, db_index=True, null=True, blank=True)
    class Meta:
        db_table = 'api_misscalls'