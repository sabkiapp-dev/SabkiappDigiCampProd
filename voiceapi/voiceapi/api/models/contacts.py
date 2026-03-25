from django.db import models
from django.db.models import UniqueConstraint
from django.core.exceptions import ValidationError



def phone_number_validator(value):
    if len(value) != 10:
        raise ValidationError("Phone number must be 10 digits long.")
    if not value.isdigit() or int(value[0]) <= 5:
        raise ValidationError("Phone number must start with a digit greater than 5.")



class Contacts(models.Model):
    id = models.BigAutoField(primary_key=True, db_index=True)
    name = models.CharField(max_length=255, null=True, db_index=True, blank=True)
    phone_number = models.CharField(max_length=10, null=False, validators=[phone_number_validator], db_index=True) 
    user_id = models.IntegerField(null=False, db_index=True)
    category_1 = models.CharField(max_length=50, blank=True, default="Others", db_index=True)
    category_2 = models.CharField(max_length=50, blank=True, default="Others", db_index=True)
    category_3 = models.CharField(max_length=50, blank=True, default="Others", db_index=True)
    category_4 = models.CharField(max_length=50, blank=True, default="Others", db_index=True)
    category_5 = models.CharField(max_length=50, blank=True, default="Others", db_index=True)
    status = models.IntegerField(null=True, default=1, db_index=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['phone_number', 'user_id'], name='unique_phone_per_user')
        ]
        db_table = 'api_contacts'

    def __str__(self):
        return self.name

