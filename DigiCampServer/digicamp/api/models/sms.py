# models.py
from django.db import models
from .campaign import Campaign  # Import the Campaign model

class Sms(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    content = models.TextField()
    content_length = models.IntegerField()  # Assuming content_length should be an Integer
    modified_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
