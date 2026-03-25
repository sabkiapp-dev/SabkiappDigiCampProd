from django.db import models
from .users import Users


class UserHosts(models.Model):
    user_id = models.ForeignKey(Users, on_delete=models.CASCADE, db_index=True) #related_name="hosts"
    host = models.CharField(max_length=255, db_index=True)
    system_password = models.CharField(max_length=255, db_index=True)
    priority = models.IntegerField(default=0, db_index=True)
    status = models.IntegerField(default=1, db_index=True)
    allow_sms = models.IntegerField(default=0, db_index=True)


    def __str__(self):
        return f"UserHosts(id={self.id}, user_id={self.user_id}, host={self.host}, system_password={self.system_password})"

    class Meta:
        unique_together = ('user_id', 'host')
        unique_together = ('host', 'priority')
