from django.db import models
from ..models.campaign import Campaign
from django.conf import settings


class Voices(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_index=True)
    voice_name = models.CharField(max_length=255, verbose_name='voice_name', db_index=True)
    voice_desc = models.TextField(null=True, blank=True, verbose_name='voice_desc')
    path = models.CharField(max_length=500, db_index=True)
    modified_at = models.DateTimeField(auto_now=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.IntegerField(default=1, db_index=True)

    def __str__(self):
        return self.voice_name

    class Meta:
        verbose_name = 'Voice'
        verbose_name_plural = 'Voices'
        unique_together = ('user', 'voice_name')
        db_table = 'api_audios'    