from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SATARK_", env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./satark_dev.db"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 60 * 60 * 24 * 30
    auth_challenge_ttl_seconds: int = 120

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    firebase_credentials_json: str = ""

    rate_limit_per_minute: int = 60

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
