from django.db import models


class SimInformation(models.Model):
    host = models.CharField(max_length=100, db_index=True)
    sim_imsi = models.CharField(max_length=100, db_index=True)
    phone_no = models.CharField(max_length=15, db_index=True, blank=True, null=True)
    sms_backup_date = models.DateField(null=True, blank=True, default="2024-02-17", db_index=True)
    sms_balance = models.IntegerField(null=True, blank=True, default=100, db_index=True)
    validity = models.DateField(null=True, blank=True, db_index=True)
    last_validity_check = models.DateTimeField(null=True, blank=True, default="2024-02-17 11:34:14", db_index=True)
    calls_made_total = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    calls_made_today = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    call_time_total = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    call_time_today = models.IntegerField(null=True, blank=True, default=0, db_index=True)
    call_status_date = models.DateField(null=True, blank=True, default="2024-02-17", db_index=True)
    last_call_time = models.DateTimeField(null=True, blank=True, default="2024-02-17 11:34:14", db_index=True)
    today_block_status = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=0.0, db_index=True)
    call_after = models.IntegerField(null=True, blank=True, default=20, db_index=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['host', 'sim_imsi'], name='unique_host_sim_imsi')
        ]

    def __str__(self):
        return self.host
