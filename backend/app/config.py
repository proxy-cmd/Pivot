from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-3.5-flash'
    cors_origins: str = 'http://localhost:5173'
    google_client_id: str = ''
    google_client_secret: str = ''
    google_redirect_uri: str = 'http://localhost:8000/api/auth/google/callback'
    jwt_secret: str = ''
    jwt_issuer: str = 'pivot-api'
    jwt_audience: str = 'pivot-web'
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    cookie_secure: bool = False
    frontend_url: str = 'http://localhost:5173'
    model_config = SettingsConfigDict(env_file=('backend/.env', '.env'), extra='ignore')

    @field_validator('cors_origins')
    @classmethod
    def require_origins(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('CORS_ORIGINS must contain at least one trusted origin.')
        return value

    def missing_auth_settings(self) -> list[str]:
        required = {'GOOGLE_CLIENT_ID': self.google_client_id, 'GOOGLE_CLIENT_SECRET': self.google_client_secret, 'JWT_SECRET': self.jwt_secret}
        return [name for name, value in required.items() if not value]


@lru_cache
def get_settings():
    return Settings()
