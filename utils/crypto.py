# utils/crypto.py
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# SALT fisso (non segreto, ma necessario per la derivazione)
SALT = b"RistoSmartSalt2025"

# Ottiene la chiave di crittografia dal file .env
def get_fernet():
    # Recupera la chiave segreta dall'ambiente
    secret = os.getenv("BANK_DATA_SECRET")
    if not secret:
        raise ValueError("❌ Variabile BANK_DATA_SECRET non impostata nel file .env")

    # Deriva una chiave di 32 byte usando PBKDF2HMAC
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return Fernet(key)

# Crittografa una stringa
def encrypt_data(data: str) -> str:
    f = get_fernet()
    return f.encrypt(data.encode()).decode()

# Decrittografa una stringa
def decrypt_data(encrypted_data: str) -> str:
    f = get_fernet()
    return f.decrypt(encrypted_data.encode()).decode()