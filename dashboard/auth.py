import binascii
import hashlib
import os
import secrets


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return binascii.hexlify(salt).decode() + ":" + binascii.hexlify(dk).decode()


def verify_password(stored_hash: str, provided: str) -> bool:
    try:
        salt_hex, dk_hex = stored_hash.split(":")
    except ValueError:
        return False
    salt = binascii.unhexlify(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", provided.encode(), salt, 100_000)
    return secrets.compare_digest(binascii.hexlify(dk).decode(), dk_hex)
