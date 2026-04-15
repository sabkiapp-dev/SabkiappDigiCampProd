from django.db import models

class ActiveCampaignHosts(models.Model):
    campaign = models.ForeignKey('Campaign', on_delete=models.CASCADE)
    host = models.ForeignKey('UserHosts', on_delete=models.CASCADE)
    status = models.IntegerField(default=0, db_index=True)

    class Meta:
        verbose_name = "Active Campaign Host"
        verbose_name_plural = "Active Campaign Hosts"

    def __str__(self):
        return f"{self.campaign} - {self.host} - {self.status}"