from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-2.0-flash'
    cors_origins: str = 'http://localhost:5173'
    model_config = SettingsConfigDict(env_file=('backend/.env', '.env'), extra='ignore')


@lru_cache
def get_settings():
    return Settings()
