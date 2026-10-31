from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # "production" turns on the guardrails that refuse a weak configuration
    app_env: str = "development"

    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # set true only when a reverse proxy is present and it sets X-Forwarded-For
    trust_forwarded_for: bool = False

    # account lockout for wrong passwords
    login_max_attempts: int = 5
    login_lock_minutes: int = 15

    # connection pool and driver limits
    db_pool_size: int = 10
    db_pool_max_overflow: int = 10
    db_connect_timeout_seconds: int = 5

    # object storage (S3-compatible: MinIO in dev, Cloudflare R2 / Backblaze B2 in production)
    s3_endpoint_url: str | None = None
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "gyansankalp-private"
    s3_region: str = "us-east-1"
    s3_create_bucket: bool = False

    # upload and conversion limits
    max_upload_mb: int = 50
    max_pdf_pages: int = 800

    # comma-separated list of frontend origins allowed to call the API
    cors_origins: str = "http://localhost:5173,http://localhost:5174"

    # /docs and /openapi.json are useful in development and a map in production
    expose_docs: bool = False

    # only set true when the API is genuinely served over HTTPS end to end
    hsts_enabled: bool = False

    # initial admin setup (one-time use, remove after first startup)
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None
    initial_admin_name: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_is_long_enough(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters. Generate one with "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

    # "none" and asymmetric names both turn the token into something the
    # verifier no longer checks the way the signer signed it.
    @field_validator("jwt_algorithm")
    @classmethod
    def jwt_algorithm_is_hmac(cls, value: str) -> str:
        if value not in {"HS256", "HS384", "HS512"}:
            raise ValueError("JWT_ALGORITHM must be HS256, HS384 or HS512")
        return value

    @model_validator(mode="after")
    def production_refuses_weak_settings(self) -> "Settings":
        if self.app_env != "production":
            return self

        problems: list[str] = []
        if len(self.jwt_secret) < 48:
            problems.append("JWT_SECRET must be at least 48 characters in production")
        if "sslmode=" not in self.database_url or "sslmode=disable" in self.database_url:
            problems.append("DATABASE_URL must set sslmode=require (or verify-full) in production")
        if self.s3_endpoint_url and not self.s3_endpoint_url.startswith("https://"):
            problems.append("S3_ENDPOINT_URL must be https in production")
        for origin in self.cors_origin_list:
            if not origin.startswith("https://"):
                problems.append(f"CORS_ORIGINS entry is not https: {origin}")
        if self.expose_docs:
            problems.append("EXPOSE_DOCS must be false in production")
        if problems:
            raise ValueError("unsafe production configuration: " + "; ".join(problems))
        return self


settings = Settings()
