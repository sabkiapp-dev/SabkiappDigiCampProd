from django.db import models
from .campaign import Campaign  # Assuming the Campaign model is in a file named campaign.py
from .voices import Voices  # Assuming the Voices model is in a file named voices.py
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from .sms_template import SmsTemplate

class DialPlan(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, db_index=True)
    extension_id = models.IntegerField(null=True, blank=True, db_index=True)
    main_voice = models.ForeignKey(Voices, related_name='main_voice', on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    option_voice = models.ForeignKey(Voices, related_name='option_voice_id', on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    dtmf_0 = models.IntegerField(null=True, blank=True, db_index=True)
    dtmf_1 = models.IntegerField(null=True, blank=True, db_index=True)
    dtmf_2 = models.IntegerField(null=True, blank=True, db_index=True)
    dtmf_3 = models.IntegerField(null=True, blank=True, db_index=True)
    dtmf_4 = models.IntegerField(null=True, blank=True, db_index=True)
    dtmf_5 = models.IntegerField(null=True, blank=True, db_index=True)
    dtmf_6 = models.IntegerField(null=True, blank=True, db_index=True)
    dtmf_7 = models.IntegerField(null=True, blank=True, db_index=True)
    dtmf_8 = models.IntegerField(null=True, blank=True, db_index=True)
    dtmf_9 = models.IntegerField(null=True, blank=True, db_index=True)
    template = models.ForeignKey(SmsTemplate, related_name='template_id', on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    sms_after = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(-2), MaxValueValidator(9)], db_index=True)
    modified_at = models.DateTimeField(auto_now=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    name_spell  = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(2)], default=0, db_index=True)
    continue_to = models.IntegerField(null=True, blank=True, db_index=True) 

    class Meta:
        unique_together = ('campaign', 'extension_id',)

    def __str__(self):
        return f'DialPlan for Campaign: {self.campaign_id}'