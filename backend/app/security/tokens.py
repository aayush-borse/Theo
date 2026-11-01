"""Minimal HS256 JWT implementation with expiry validation."""
import base64, hashlib, hmac, json, os, time

SECRET=os.getenv("THEO_JWT_SECRET", "")

def _b64(value: bytes) -> str: return base64.urlsafe_b64encode(value).rstrip(b"=").decode()
def issue_token(subject: str, role: str, secret: str|None=None, ttl: int=3600) -> str:
    key=(secret or SECRET).encode()
    if len(key)<32: raise ValueError("THEO_JWT_SECRET must be at least 32 characters")
    header=_b64(json.dumps({"alg":"HS256","typ":"JWT"},separators=(",",":")).encode())
    payload=_b64(json.dumps({"sub":subject,"role":role,"iat":int(time.time()),"exp":int(time.time())+ttl},separators=(",",":")).encode())
    signing=f"{header}.{payload}".encode(); sig=_b64(hmac.new(key,signing,hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"

def verify_token(token: str, secret: str|None=None) -> dict:
    key=(secret or SECRET).encode()
    if len(key)<32: raise ValueError("THEO_JWT_SECRET must be configured with 32+ characters")
    try:
        h,p,s=token.split("."); signing=f"{h}.{p}".encode(); expected=_b64(hmac.new(key,signing,hashlib.sha256).digest())
        if not hmac.compare_digest(expected,s): raise ValueError("Invalid token signature")
        pad=lambda x: x+"="*((4-len(x)%4)%4)
        header=json.loads(base64.urlsafe_b64decode(pad(h))); claims=json.loads(base64.urlsafe_b64decode(pad(p)))
        if header.get("alg")!="HS256" or int(claims.get("exp",0))<int(time.time()): raise ValueError("Expired or unsupported token")
        return claims
    except Exception as exc: raise ValueError("Invalid or expired bearer token") from exc
