from django.db import models
from django.conf import settings

class SmsTemplate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_index=True)
    template_name = models.CharField(max_length=766, db_index=True)
    template = models.TextField()
    status  = models.IntegerField(default=1, db_index=True)

    class Meta:
        unique_together = ('user', 'template_name')