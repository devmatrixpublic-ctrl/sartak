from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


DEV_JWT_SECRET = "dev-only-secret-not-for-production-use"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SATARK_", env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./satark_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    # Optional second connection for `alembic upgrade head` only. When the runtime URL is a DML-only role
    # (ops/security/db_roles.sql) migrations still need DDL rights. Empty = use database_url.
    migration_database_url: str = ""

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
    # Mule fan-in: hold a payment when this many OTHER devices paid the same payee within the window. 0 disables.
    mule_fanin_threshold: int = 3
    mule_fanin_window_minutes: int = 60

    # Number of proxies (e.g. Render's load balancer) that append to X-Forwarded-For. 0 = ignore the header (safe default). Set it only
    # after checking how many hops the platform adds; a value that is too high lets callers choose their own rate-limit bucket.
    trusted_proxy_hops: int = 0

    # Request-body caps in bytes. The largest legitimate body is /auth/device (up to 6 attestation certificates, ~12 KB base64).
    max_body_bytes: int = 64 * 1024
    webhook_max_body_bytes: int = 256 * 1024

    # Device auth (Member 4, contracts/auth.md). Identity of the release app for attestation check 6.
    auth_expected_package: str = ""
    auth_expected_signing_sha256: str = ""      # comma-separated lowercase hex SHA-256 digests
    auth_attestation_roots: str = ""       # PEM bundle of the pinned Google attestation roots
    auth_require_hardware: bool = True
    auth_enable_dev_token: bool = False         # dev only, refused elsewhere (see the dev-token stub in auth/routes.py)

    @property
    def effective_migration_url(self) -> str:
        return self.migration_database_url or self.database_url

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
