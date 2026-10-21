from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


DEV_JWT_SECRET = "dev-only-secret-not-for-production-use"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SATARK_", env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./satark_dev.db"
    redis_url: str = "redis://localhost:6379/0"

    # Refused at boot outside dev (app/auth/config.py); the default exists only for local runs.
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 60 * 60 * 24 * 30
    auth_challenge_ttl_seconds: int = 120

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    firebase_credentials_json: str = ""

    rate_limit_per_minute: int = 60

    # Device auth (Member 4, contracts/auth.md). Identity of the release app for attestation check 6.
    auth_expected_package: str = ""
    auth_expected_signing_sha256: str = ""      # comma-separated lowercase hex SHA-256 digests
    auth_attestation_roots: str = ""       # PEM bundle of the pinned Google attestation roots
    auth_require_hardware: bool = True
    auth_enable_dev_token: bool = False         # SATARK_STUB: dev only, refused elsewhere

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
