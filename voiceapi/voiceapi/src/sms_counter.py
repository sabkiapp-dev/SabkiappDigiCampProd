import re

class SmsCounter:
    gsm7bitChars = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
    gsm7bitExChar = "^{}\\[~\\]|€"
    gsm7bitRegExp = re.compile("^[" + re.escape(gsm7bitChars) + "]*$")
    gsm7bitExRegExp = re.compile("^[" + re.escape(gsm7bitChars + gsm7bitExChar) + "]*$")
    gsm7bitExOnlyRegExp = re.compile("^[" + re.escape(gsm7bitExChar) + "]*$")
    GSM_7BIT = "GSM_7BIT"
    GSM_7BIT_EX = "GSM_7BIT_EX"
    UTF16 = "UTF16"
    messageLength = {
        GSM_7BIT: 160,
        GSM_7BIT_EX: 160,
        UTF16: 70
    }
    multiMessageLength = {
        GSM_7BIT: 153,
        GSM_7BIT_EX: 153,
        UTF16: 67
    }

    @classmethod
    def count(cls, text):
        encoding = cls.detect_encoding(text)
        length = len(text)

        if encoding == cls.GSM_7BIT_EX:
            length += cls.count_gsm7bit_ex(text)

        per_message = cls.messageLength[encoding]

        if length > per_message:
            per_message = cls.multiMessageLength[encoding]

        sms_count = (length + per_message - 1) // per_message
        remaining = per_message * sms_count - length

        if remaining == 0 and sms_count == 0:
            remaining = per_message

        return {
            "encoding": encoding,
            "length": length,
            "per_message": per_message,
            "remaining": remaining,
            "sms_count": sms_count
        }

    @classmethod
    def detect_encoding(cls, text):
        if cls.gsm7bitRegExp.match(text):
            return cls.GSM_7BIT
        elif cls.gsm7bitExRegExp.match(text):
            return cls.GSM_7BIT_EX
        else:
            return cls.UTF16

    @classmethod
    def count_gsm7bit_ex(cls, text):
        chars = [char for char in text if cls.gsm7bitExOnlyRegExp.match(char)]
        return len(chars)
    
    @classmethod
    def show_details(cls, result):
        print(f"Message Encoding: {result['encoding']}")
        print(f"Message Length: {result['length']}")
        print(f"Sms_count: {result['sms_count']}")
        print(f"Remaining Characters: {result['remaining']}")
        print(f"Characters per Message: {result['per_message']}")

        if result['encoding'] == SmsCounter.GSM_7BIT_EX:
            gsm7bit_ex_count = SmsCounter.count_gsm7bit_ex(cls.message)
            print(f"GSM 7bit Ex-Only Characters Count: {gsm7bit_ex_count}")

        print("Checking SMS length and type complete.")
