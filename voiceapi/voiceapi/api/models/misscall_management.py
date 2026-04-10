from django.db import models
from django.conf import settings

class MisscallManagement(models.Model):
    description = models.TextField(null=True, blank=True)
    operator = models.CharField(max_length=11, db_index=True)
    associated_number = models.CharField(max_length=15, db_index=True, null=True, blank=True)
    user = models.ForeignKey('Users', on_delete=models.CASCADE, db_index=True)
    campaign_associated = models.ForeignKey('Campaign', on_delete=models.CASCADE, db_index=True, null=True, blank=True)
    status = models.IntegerField(db_index=True, default=1)
    management_id = models.CharField(max_length=10, unique=True)
    update_date = models.DateField(null=True, blank=True)
    class Meta:
        db_table = 'api_misscall_management'