from django.db import models
from ..models.users import Users
from datetime import date
from django.core.validators import MinValueValidator, MaxValueValidator
class Campaign(models.Model):

    LANGUAGES = [
        ('hi', 'Hindi'),
        ('en', 'English'),
        ('pa', 'Punjabi'),
        ('mr', 'Marathi'),
        ('gu', 'Gujarati'),
        ('bn', 'Bengali'),
        ('ta', 'Tamil'),
        ('te', 'Telugu'),
        ('ml', 'Malayalam'),
        ('ka', 'Kannada'),
        ('as', 'Assamese'),
        ('or', 'Oriya'),
    ]
    name = models.CharField(max_length=255, db_index=True)
    name_spell = models.IntegerField(null=True, blank=True, db_index=True, default=0)
    description = models.TextField(null=True)
    call_cut_time = models.IntegerField(db_index=True)
    start_time = models.TimeField(db_index=True)
    end_time = models.TimeField(db_index=True)
    start_date = models.DateField(default=date(2024, 1, 1), db_index=True)
    end_date = models.DateField(default=date(2050, 12, 31), db_index=True)
    campaign_priority = models.IntegerField(default=1, db_index=True)
    status = models.IntegerField(default=0, db_index=True)
    user = models.ForeignKey(Users, on_delete=models.CASCADE, db_index=True)
    modified_at = models.DateTimeField(auto_now=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    wrong_key_voice = models.ForeignKey('Voices', on_delete=models.CASCADE, related_name='wrong_key_voice', null=True, db_index=True)
    no_key_voice = models.ForeignKey('Voices', on_delete=models.CASCADE, related_name='no_key_voice', null=True, db_index=True)
    contacts_count = models.IntegerField(default=0, db_index=True)
    language = models.CharField(max_length=2, choices=LANGUAGES, default='hi', db_index=True)
    allow_repeat = models.IntegerField(default=0, db_index=True)
    class Meta:
        unique_together = (('name', 'user'),)
    
    def unique_error_message(self, model_class, unique_check):
        if model_class == type(self) and unique_check == ('name', 'user'):
            return 'This Campaign name {}, already exists'.format(self.name)
        else:
            return super().unique_error_message(model_class, unique_check)

    def get_language_display(self):
        lang_dict = dict(self.LANGUAGES)
        return lang_dict.get(self.language, '')
    def __str__(self):
        return self.name
