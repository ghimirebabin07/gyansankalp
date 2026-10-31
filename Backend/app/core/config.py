

from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

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

    # initial admin setup (one-time use, remove after first startup)
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None
    initial_admin_name: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()