from base64 import b64encode, b64decode
import hashlib
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad
from django.conf import settings

password = settings.PHONE_ENCRYPTER_KEY

def encrypt(plain_text):
    # Generate a key from the password
    key = hashlib.sha1(password.encode()).digest()[:16]
    cipher = AES.new(key, AES.MODE_ECB)
    cipher_text = cipher.encrypt(pad(plain_text.encode(), AES.block_size))
    return b64encode(cipher_text).decode()

def decrypt(cipher_text, password):
    # Generate a key from the password
    key = hashlib.sha1(password.encode()).digest()[:16]
    cipher = AES.new(key, AES.MODE_ECB)
    plain_text = unpad(cipher.decrypt(b64decode(cipher_text)), AES.block_size)
    return plain_text.decode()


if __name__ == "__main__":
    phone = "9971389164"
    password = "DDIjoS0ckWyXJHexm6OYdK8XZy8p9YDo"

    print("Phone number: ", phone)

    encrypted_phone = encrypt(phone, password)
    print("Encrypted phone number: ", encrypted_phone)

    decrypted_phone = decrypt(encrypted_phone, password)
    print("Decrypted phone number: ", decrypted_phone)


















# import os
# import string
# import random


# def encrypt_phone(number, password):
#     # Create a mapping of digits to alphanumeric characters
#     chars = string.ascii_letters + string.digits
#     random.seed(password)
#     shuffled_chars = random.sample(chars, len(chars))
#     mapping = str.maketrans(string.digits, ''.join(shuffled_chars[:10]))

#     # Convert the number to a string and translate it using the mapping
#     return str(number).translate(mapping)


# def decrypt_phone(encrypted, password):
#     # Create a mapping of alphanumeric characters to digits
#     chars = string.ascii_letters + string.digits
#     random.seed(password)
#     shuffled_chars = random.sample(chars, len(chars))
#     mapping = str.maketrans(''.join(shuffled_chars[:10]), string.digits)

#     # Translate the encrypted string using the mapping
#     return encrypted.translate(mapping)

# from Crypto.Cipher import AES
# from Crypto.Util.Padding import pad, unpad
# from Crypto.Random import get_random_bytes
# from base64 import b64encode, b64decode


# def encrypt_with_password(message, key_hex):
#     key = bytes.fromhex(key_hex)  # Convert hex string back to bytes
#     cipher = AES.new(key, AES.MODE_ECB)
#     ct_bytes = cipher.encrypt(pad(message.encode(), AES.block_size))
#     ct = b64encode(ct_bytes).decode('utf-8')
#     return ct


# def decrypt_with_password(ciphertext, key_hex):
#     key = bytes.fromhex(key_hex)  # Convert hex string back to bytes
#     cipher = AES.new(key, AES.MODE_ECB)
#     pt_bytes = cipher.decrypt(b64decode(ciphertext))
#     pt = unpad(pt_bytes, AES.block_size).decode('utf-8')
#     return pt

# encrypted = encrypt_with_password('9934445076', '026fb9b3ccfa21fcae160fb6575ee14729667edfe3246f3735f7874f98427968')

# print(encrypted)

# decrypted = decrypt_with_password(encrypted, '026fb9b3ccfa21fcae160fb6575ee14729667edfe3246f3735f7874f98427968')
# print(decrypted)