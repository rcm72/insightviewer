import os, time, secrets
from jose import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
EXPIRE_SECONDS = 3600

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "Lax")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False

def issue_token(user_uid: str, email: str, project: str, role: str = "user") -> str:
    now = int(time.time())
    payload = {"sub": user_uid, "email": email, "project": project, "role": role,
               "iat": now, "exp": now + EXPIRE_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
