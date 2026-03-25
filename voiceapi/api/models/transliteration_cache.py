import hashlib
from django.db import models


class TransliterationCache(models.Model):
    # पूरा स्रोत-टेक्स्ट (इस पर कोई विशेष index नहीं)
    source_text = models.TextField()


    transliterated_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "transliteration_cache"
        # ❌  TextField पर index हटाया → MySQL prefix-length issue ख़त्म
        # indexes = [...]

    def save(self, *args, **kwargs):
        # हर बार hash री-कैल्कुलेट (idempotent)
        self.text_hash = hashlib.sha256(
            (self.source_text or "").encode("utf-8")
        ).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return (self.source_text or "")[:50]
