from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from .auth import authenticate_request, issue_access_token, new_refresh_token, require_auth_configuration, require_auth_database, token_digest
from .config import get_settings
from .store import consume_refresh_session, create_refresh_session, revoke_refresh_session, upsert_google_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/auth', tags=['authentication'])


def _oauth() -> OAuth:
    settings = get_settings()
    client = OAuth()
    client.register('google', client_id=settings.google_client_id, client_secret=settings.google_client_secret, server_metadata_url='https://accounts.google.com/.well-known/openid-configuration', client_kwargs={'scope': 'openid email profile'})
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
    if origin and origin.rstrip('/') not in {value.strip().rstrip('/') for value in get_settings().cors_origins.split(',')}:
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
        token = await _oauth().create_client('google').authorize_access_token(request)
        claims = token.get('userinfo') or await _oauth().create_client('google').userinfo(token=token)
        if not claims.get('sub') or not claims.get('email') or not claims.get('email_verified'):
            raise HTTPException(403, 'Google did not provide a verified email address.')
        user = upsert_google_user(claims['sub'], claims['email'], claims.get('name') or claims['email'], claims.get('picture'))
        refresh_token = new_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days)
        create_refresh_session(user['id'], token_digest(refresh_token), expires_at.isoformat(), request.headers.get('user-agent', '')[:500], request.client.host if request.client else None)
        response = _redirect_to_frontend()
        response.set_cookie('pivot_refresh', refresh_token, httponly=True, secure=get_settings().cookie_secure, samesite='lax', max_age=get_settings().refresh_token_days * 86400, path='/api/auth')
        response.set_cookie('pivot_access', issue_access_token(user['id']), httponly=True, secure=get_settings().cookie_secure, samesite='lax', max_age=get_settings().access_token_minutes * 60, path='/')
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
    refresh_token = request.cookies.get('pivot_refresh')
    if not refresh_token:
        raise HTTPException(401, 'Refresh token is missing.')
    session = consume_refresh_session(token_digest(refresh_token))
    if not session:
        raise HTTPException(401, 'Refresh token is invalid or expired.')
    user = session['user']
    replacement = new_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days)
    create_refresh_session(user['id'], token_digest(replacement), expires_at.isoformat(), request.headers.get('user-agent', '')[:500], request.client.host if request.client else None, session['id'])
    response = Response(status_code=204)
    response.set_cookie('pivot_refresh', replacement, httponly=True, secure=get_settings().cookie_secure, samesite='lax', max_age=get_settings().refresh_token_days * 86400, path='/api/auth')
    response.set_cookie('pivot_access', issue_access_token(user['id']), httponly=True, secure=get_settings().cookie_secure, samesite='lax', max_age=get_settings().access_token_minutes * 60, path='/')
    return response


@router.post('/logout', status_code=204)
def logout(request: Request):
    _require_trusted_origin(request)
    token = request.cookies.get('pivot_refresh')
    if token:
        revoke_refresh_session(token_digest(token))
    response = Response(status_code=204)
    response.delete_cookie('pivot_refresh', path='/api/auth')
    response.delete_cookie('pivot_access', path='/')
    return response


@router.get('/me')
def me(request: Request):
    return _public_user(authenticate_request(request))
