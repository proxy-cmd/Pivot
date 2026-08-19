from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from .auth import authenticate_request, issue_access_token, new_refresh_token, require_auth_configuration, require_auth_database, token_digest
from .core.config import get_settings
from .store import consume_refresh_session, create_refresh_session, revoke_refresh_session, upsert_google_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/auth', tags=['authentication'])
REFRESH_COOKIE = 'pivot_refresh'
ACCESS_COOKIE = 'pivot_access'


def _oauth() -> OAuth:
    settings = get_settings()
    client = OAuth()
    client.register(
        'google',
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )
    return client


def _public_user(user: dict) -> dict:
    return {key: user[key] for key in ('id', 'google_id', 'email', 'full_name', 'avatar_url', 'created_at', 'updated_at', 'last_login')}


def _redirect_to_frontend(error: str | None = None) -> RedirectResponse:
    url = get_settings().frontend_url.rstrip('/')
    if error:
        url += '?' + urlencode({'auth_error': error})
    return RedirectResponse(url, status_code=302)


def _require_trusted_origin(request: Request) -> None:
    origin = request.headers.get('origin')
    if not origin:
        return

    allowed_origins = {value.rstrip('/') for value in get_settings().allowed_origins()}
    if origin.rstrip('/') not in allowed_origins:
        raise HTTPException(403, 'Request origin is not allowed.')


@router.get('/google/login')
async def google_login(request: Request):
    require_auth_configuration()
    require_auth_database()
    client = _oauth().create_client('google')
    return await client.authorize_redirect(request, get_settings().google_redirect_uri)


@router.get('/google/callback')
async def google_callback(request: Request):
    try:
        require_auth_configuration()
        claims = await google_claims(request)
        user = save_google_user(claims)
        refresh_token = create_session(user['id'], request)
        response = _redirect_to_frontend()
        set_auth_cookies(response, user['id'], refresh_token)
        return response
    except HTTPException as error:
        logger.warning('Google authentication rejected: %s', error.detail)
        return _redirect_to_frontend('google_login_failed')
    except Exception:
        logger.exception('Google authentication callback failed')
        return _redirect_to_frontend('google_login_failed')


@router.post('/refresh')
def refresh(request: Request):
    _require_trusted_origin(request)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(401, 'Refresh token is missing.')

    session = consume_refresh_session(token_digest(refresh_token))
    if not session:
        raise HTTPException(401, 'Refresh token is invalid or expired.')

    user = session['user']
    replacement = create_session(user['id'], request, session['id'])
    response = Response(status_code=204)
    set_auth_cookies(response, user['id'], replacement)
    return response


@router.post('/logout', status_code=204)
def logout(request: Request):
    _require_trusted_origin(request)
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        revoke_refresh_session(token_digest(token))

    response = Response(status_code=204)
    response.delete_cookie(REFRESH_COOKIE, path='/api/auth')
    response.delete_cookie(ACCESS_COOKIE, path='/')
    return response


@router.get('/me')
def me(request: Request):
    return _public_user(authenticate_request(request))


async def google_claims(request: Request) -> dict:
    client = _oauth().create_client('google')
    token = await client.authorize_access_token(request)
    claims = token.get('userinfo') or await client.userinfo(token=token)
    if not claims.get('sub') or not claims.get('email') or not claims.get('email_verified'):
        raise HTTPException(403, 'Google did not provide a verified email address.')
    return claims


def save_google_user(claims: dict) -> dict:
    return upsert_google_user(
        claims['sub'],
        claims['email'],
        claims.get('name') or claims['email'],
        claims.get('picture'),
    )


def create_session(user_id: str, request: Request, parent_id: str | None = None) -> str:
    settings = get_settings()
    refresh_token = new_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_days)
    create_refresh_session(
        user_id,
        token_digest(refresh_token),
        expires_at.isoformat(),
        request.headers.get('user-agent', '')[:500],
        request.client.host if request.client else None,
        parent_id,
    )
    return refresh_token


def set_auth_cookies(response: Response, user_id: str, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite='lax',
        max_age=settings.refresh_token_days * 86400,
        path='/api/auth',
    )
    response.set_cookie(
        ACCESS_COOKIE,
        issue_access_token(user_id),
        httponly=True,
        secure=settings.cookie_secure,
        samesite='lax',
        max_age=settings.access_token_minutes * 60,
        path='/',
    )
