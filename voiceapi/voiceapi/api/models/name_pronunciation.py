from django.db import models

class NamePronunciation(models.Model):
    name = models.CharField(max_length=255, unique=True, db_index=True)
    user = models.ForeignKey('Users', on_delete=models.CASCADE, null=True, blank=True, db_index=True)

    def __str__(self):
        return self.name