from __future__ import annotations

import hashlib
import logging
import secrets
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, Request

from .core.config import get_settings
from .store import get_user

logger = logging.getLogger(__name__)
current_user_id: ContextVar[str | None] = ContextVar('current_user_id', default=None)


def require_auth_configuration() -> None:
    settings = get_settings()
    missing = settings.missing_auth_settings()
    if missing:
        raise HTTPException(503, f'Authentication is unavailable: missing {", ".join(missing)}.')
    try:
        settings.validate_auth_security()
    except ValueError as error:
        raise HTTPException(503, f'Authentication is unavailable: {error}') from error


def require_auth_database() -> None:
    try:
        get_settings().require_database_url()
    except RuntimeError as error:
        raise HTTPException(503, 'Authentication is unavailable: DATABASE_URL must be configured.') from error


def issue_access_token(user_id: str) -> str:
    settings = get_settings()
    require_auth_configuration()
    now = datetime.now(UTC)
    return jwt.encode({'sub': user_id, 'iss': settings.jwt_issuer, 'aud': settings.jwt_audience, 'iat': now, 'nbf': now, 'exp': now + timedelta(minutes=settings.access_token_minutes), 'jti': secrets.token_urlsafe(16), 'type': 'access'}, settings.jwt_secret, algorithm='HS256')


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    require_auth_configuration()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'], audience=settings.jwt_audience, issuer=settings.jwt_issuer, options={'require': ['sub', 'exp', 'iat', 'nbf', 'jti']})
    except jwt.PyJWTError as error:
        raise HTTPException(401, 'Invalid or expired access token.', headers={'WWW-Authenticate': 'Bearer'}) from error
    if payload.get('type') != 'access':
        raise HTTPException(401, 'Invalid access token.', headers={'WWW-Authenticate': 'Bearer'})
    return payload


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def authenticate_request(request: Request) -> dict[str, Any]:
    authorization = request.headers.get('Authorization', '')
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer':
        token = request.cookies.get('pivot_access', '')
    if not token:
        raise HTTPException(401, 'Authentication required.', headers={'WWW-Authenticate': 'Bearer'})
    payload = decode_access_token(token)
    user = get_user(payload['sub'])
    if not user:
        raise HTTPException(401, 'User session is no longer valid.', headers={'WWW-Authenticate': 'Bearer'})
    return user
