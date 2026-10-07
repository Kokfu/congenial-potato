import hashlib
import hmac
import secrets
from datetime import timedelta
from pathlib import Path
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .db import db_session
from .models import AuditEvent, LoginAttempt, Owner, OwnerSession, now

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def bootstrap_owner(db: Session, password_file: Path) -> None:
    if db.scalar(select(Owner.id).limit(1)):
        if db.get(LoginAttempt, 'owner') is None:
            db.add(LoginAttempt(key='owner', failures=0))
            db.commit()
        return
    password = password_file.read_text().rstrip('\n')
    if len(password) < 12:
        raise ValueError('Initial owner password must have at least 12 characters')
    db.add(Owner(username='owner', password_hash=_hasher.hash(password)))
    db.add(LoginAttempt(key='owner', failures=0))
    db.commit()


def login(db: Session, password: str) -> tuple[str, str]:
    attempt = db.execute(select(LoginAttempt).where(LoginAttempt.key == 'owner').with_for_update()).scalar_one_or_none()
    if attempt is None:
        attempt = LoginAttempt(key='owner', failures=0)
        db.add(attempt)
        db.flush()
    if attempt.blocked_until and attempt.blocked_until > now():
        raise HTTPException(429, 'Login temporarily blocked')
    owner = db.scalar(select(Owner).where(Owner.username == 'owner'))
    try:
        valid = owner is not None and _hasher.verify(owner.password_hash, password)
    except (VerifyMismatchError, VerificationError):
        valid = False
    if not valid:
        attempt.failures += 1
        if attempt.failures >= 5:
            attempt.blocked_until = now() + timedelta(minutes=5)
            attempt.failures = 0
        db.add(AuditEvent(actor='anonymous', action='auth.login', resource='owner', outcome='denied'))
        db.commit()
        raise HTTPException(401, 'Invalid credentials')
    attempt.failures = 0
    attempt.blocked_until = None
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(OwnerSession(owner_id=owner.id, token_hash=digest(token), csrf_hash=digest(csrf), expires_at=now() + timedelta(hours=get_settings().session_hours)))
    db.add(AuditEvent(actor=owner.id, action='auth.login', resource='owner', outcome='allowed'))
    db.commit()
    return token, csrf


def cookie_name() -> str:
    return '__Host-workforce_session' if get_settings().session_cookie_secure else 'workforce_session'


def set_auth_cookies(response: Response, token: str, csrf: str) -> None:
    settings = get_settings()
    common = {'secure': settings.session_cookie_secure, 'samesite': 'strict', 'path': '/', 'max_age': settings.session_hours * 3600}
    response.set_cookie(cookie_name(), token, httponly=True, **common)
    response.set_cookie('workforce_csrf', csrf, httponly=False, **common)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(cookie_name(), path='/')
    response.delete_cookie('workforce_csrf', path='/')


def current_session(request: Request, db: Session = Depends(db_session)) -> OwnerSession:
    token = request.cookies.get(cookie_name())
    if not token:
        raise HTTPException(401, 'Authentication required')
    session = db.scalar(select(OwnerSession).where(OwnerSession.token_hash == digest(token)))
    if not session or session.revoked_at or session.expires_at <= now():
        raise HTTPException(401, 'Authentication required')
    return session


def require_csrf(request: Request, session: OwnerSession = Depends(current_session)) -> OwnerSession:
    supplied = request.headers.get('x-csrf-token', '')
    cookie = request.cookies.get('workforce_csrf', '')
    if not supplied or not cookie or not hmac.compare_digest(supplied, cookie) or not hmac.compare_digest(digest(supplied), session.csrf_hash):
        raise HTTPException(403, 'CSRF token required')
    return session


def require_origin(request: Request) -> None:
    if request.headers.get('origin') != get_settings().allowed_origin:
        raise HTTPException(403, 'Origin denied')
