"""Small dependency-light password hashing helpers using scrypt."""
import base64, hashlib, hmac, os


def hash_password(password: str) -> str:
    if len(password)<12: raise ValueError("Password must contain at least 12 characters")
    salt=os.urandom(16); digest=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1,dklen=64)
    return "scrypt$16384$"+base64.urlsafe_b64encode(salt).decode()+"$"+base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme,n,salt,digest=encoded.split("$")
        if scheme!="scrypt" or n!="16384": return False
        actual=hashlib.scrypt(password.encode(),salt=base64.urlsafe_b64decode(salt),n=2**14,r=8,p=1,dklen=64)
        return hmac.compare_digest(actual,base64.urlsafe_b64decode(digest))
    except (ValueError,TypeError): return False
