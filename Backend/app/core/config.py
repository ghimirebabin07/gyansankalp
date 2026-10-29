

from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30

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


settings = Settings()