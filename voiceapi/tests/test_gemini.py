

import google.generativeai as genai

# API key config (replace with your key or set via env var)
genai.configure(api_key="AIzaSyBilUXggzl_ib-3TvwplFhHdwDpVkl2rtU")

# Create the model
model = genai.GenerativeModel('gemini-2.5-flash')

def transliterate_to_hindi(text: str) -> str:
    """
    Transliterates any input text to standard Devanagari Hindi.
    If the text is already in Hindi, it is returned unchanged.
    The model’s reply contains *only* the final transliterated text.
    """
    prompt = (
        "You are a transliteration engine. "
        "Transliterate the following text into standard Devanagari Hindi. "
        "If it is already in Hindi, return it as-is. "
        "Respond with **only** the transliterated text—no explanations.\n\n"
        f"Text: {text}"
    )
    response = model.generate_content(prompt)
    return response.text.strip()

# Example
source_text = "लोकल"
print(transliterate_to_hindi(source_text))
