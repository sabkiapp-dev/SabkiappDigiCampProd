from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db.models import JSONField

class CustomUserManager(BaseUserManager):
    def create_user(self, mobile_number, password=None, **extra_fields):
        if not mobile_number:
            raise ValueError(('The mobile number must be set'))
        user = self.model(mobile_number=mobile_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_number, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(mobile_number, password, **extra_fields)

class Users(AbstractBaseUser, PermissionsMixin):
    name = models.CharField(max_length=255, db_index=True)
    mobile_number = models.CharField(max_length=15, unique=True, db_index=True)
    password = models.CharField(max_length=255, db_index=True)
    status = models.IntegerField(db_index=True)
    modified_at = models.DateTimeField(auto_now=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ref_id = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        related_name='referred_users', 
        null=True, 
        blank=True,
        db_index=True
    )
    
    api_key = models.CharField(max_length=255, db_index=True, null=True, blank=True)
    USERNAME_FIELD = 'mobile_number'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.mobile_number
