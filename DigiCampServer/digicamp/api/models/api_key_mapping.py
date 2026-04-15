from django.db import models


class ApiKeyMapping(models.Model):
    """
    Maps API keys to user_id + campaign_id for the add_contact API.
    """
    api_key = models.CharField(max_length=255, unique=True, db_index=True)
    user_id = models.IntegerField(db_index=True)
    campaign_id = models.BigIntegerField(db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'api_key_mapping'
        verbose_name = 'API Key Mapping'
        verbose_name_plural = 'API Key Mappings'

    def __str__(self):
        return f"{self.api_key[:10]}... -> user:{self.user_id}, campaign:{self.campaign_id}"
