"""
Utility: cached transliteration to standard Devanagari Hindi.

• पहले DB-कॅश (`TransliterationCache`) देखता है।  
• न मिले तो Gemini-2.5-flash से पूछता है और कॅश करता है।  
• हमेशा सिर्फ़ अंतिम ट्रांसलिटरेटेड टेक्स्ट देता है (बिना टिप्पणी)।
"""

from django.conf import settings
from google.generativeai import GenerativeModel, configure
from api.models import TransliterationCache
from django.db import transaction

# Gemini API सेट-अप
configure(api_key=settings.GEMINI_API_KEY)
_MODEL = GenerativeModel("gemini-2.5-flash")

_PROMPT_TEMPLATE = (
    "You are a transliteration engine. "
    "Transliterate the following text into standard Devanagari Hindi. "
    "If it is already in Hindi, return it as-is. "
    "Respond with only the transliterated text—no explanations.\n\n"
    "Text: {txt}"
)


def transliterate_hindi(text: str | None) -> str | None:
    """Return Hindi-Devanagari transliteration (cached)."""
    if not text:
        return text  # None / empty → 그대로

    src = text.strip()
    try:
        cached = TransliterationCache.objects.get(source_text=src)
        return cached.transliterated_text
    except TransliterationCache.DoesNotExist:
        pass

    prompt = _PROMPT_TEMPLATE.format(txt=src)
    try:
        response = _MODEL.generate_content(prompt)
        result = (response.text or "").strip()
        print("** transliteration result : ", result)
    except Exception as exc:
        # Fallback: यदि Gemini फेल हो गया तो original लौटाएँ
        # (लॉग करना बेहतर होगा)
        return src

    # कॅश में डालें (atomic—dup key पर race condition न हो)
    with transaction.atomic():
        TransliterationCache.objects.get_or_create(
            source_text=src,
            defaults={"transliterated_text": result},
        )

    return result
