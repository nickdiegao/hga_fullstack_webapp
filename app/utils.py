import base64
import hashlib
from cryptography.fernet import Fernet

def get_fernet(secret_key):
    digest = hashlib.sha256(secret_key.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)

def encrypt_text(fernet, value):
    if not value:
        return None
    return fernet.encrypt(value.encode()).decode()

def decrypt_text(fernet, value):
    if not value:
        return ""
    try:
        return fernet.decrypt(value.encode()).decode()
    except:
        return ""