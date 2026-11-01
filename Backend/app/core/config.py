from pydantic import Field, field_validator, model_validator
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
    # Admin tokens get their own key: one leaked student-token secret must not be
    # able to mint an admin token.
    admin_jwt_secret: str

    # set true only when a reverse proxy is present and it sets X-Forwarded-For
    trust_forwarded_for: bool = False

    # logging: JSON for a log shipper, plain text for reading in a terminal
    log_level: str = "INFO"
    log_json: bool = False

    # how long page views stay in access_logs before the worker prunes them
    access_log_days: int = 180
    # how long a dead refresh token stays for audit before it is purged
    refresh_token_purge_days: int = 7

    # account lockout for wrong passwords
    login_max_attempts: int = 5
    login_lock_minutes: int = 15

    # staff sign-in: Google proves who they are, an emailed code proves they can
    # read that mailbox. Both halves happen in the same login, minutes apart.
    admin_access_token_minutes: int = Field(15, ge=5, le=120)
    # One working day, so a night off ends the session and the code comes back.
    admin_refresh_token_days: int = Field(1, ge=1, le=30)
    admin_otp_minutes: int = Field(5, ge=1, le=15)
    admin_otp_max_attempts: int = Field(5, ge=3, le=10)
    # A code is spent or dead; the pass that lets you keep trying lives a little
    # longer, so the last code sent still has somewhere to be typed.
    admin_otp_challenge_minutes: int = Field(10, ge=5, le=30)
    admin_otp_resend_seconds: int = Field(60, ge=15, le=600)
    # how long staff action records stay before the worker prunes them
    admin_activity_log_days: int = Field(365, ge=30, le=3650)
    # The staff list itself, read only by app.scripts.seed_staff: comma-separated
    # "email:Full Name:role" entries. It lives in .env because these addresses are
    # the accounts allowed through the admin door, and a repository should not name
    # them.
    staff_roster: str = ""

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
    # a hung storage endpoint must not hold a request or a worker job open
    s3_connect_timeout_seconds: int = 5
    s3_read_timeout_seconds: int = 30

    # upload and conversion limits
    max_upload_mb: int = 50
    max_pdf_pages: int = 800

    # comma-separated list of frontend origins allowed to call the API
    cors_origins: str = "http://localhost:5173,http://localhost:5174"

    # Google sign-in. The client id is public - it is what proves an ID token was
    # issued for this site and not for someone else's app.
    google_client_id: str | None = None
    google_jwks_url: str = "https://www.googleapis.com/oauth2/v3/certs"

    # verification email: left unset, links are printed to the log instead of sent
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    mail_from: str | None = None
    # the SPA page the verification link points at
    verify_link_base: str = "http://localhost:5173/verify-email"
    email_verify_hours: int = Field(24, ge=1, le=168)

    # /docs and /openapi.json are useful in development and a map in production
    expose_docs: bool = False

    # the public catalogue is a browser-cacheable read-only list; 0 disables it
    public_cache_seconds: int = Field(30, ge=0, le=3600)

    # only set true when the API is genuinely served over HTTPS end to end
    hsts_enabled: bool = False

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

    @field_validator("admin_jwt_secret")
    @classmethod
    def admin_secret_is_separate_and_long_enough(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("ADMIN_JWT_SECRET must be at least 32 characters")
        return value

    # A typo here means every Google token fails the audience check and sign-in
    # looks broken with no obvious cause, so reject anything that is not one.
    @field_validator("google_client_id")
    @classmethod
    def google_client_id_looks_real(cls, value: str | None) -> str | None:
        if value and not value.endswith(".apps.googleusercontent.com"):
            raise ValueError(
                "GOOGLE_CLIENT_ID must be the value from Google Cloud Console, "
                "which ends in .apps.googleusercontent.com"
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

    @field_validator("log_level")
    @classmethod
    def log_level_is_known(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return normalized

    @model_validator(mode="after")
    def keys_are_distinct(self) -> "Settings":
        # Reusing the student key would make the separation only a name.
        if self.admin_jwt_secret == self.jwt_secret:
            raise ValueError("ADMIN_JWT_SECRET must differ from JWT_SECRET")
        return self

    @model_validator(mode="after")
    def production_refuses_weak_settings(self) -> "Settings":
        if self.app_env != "production":
            return self

        problems: list[str] = []
        if len(self.jwt_secret) < 48:
            problems.append("JWT_SECRET must be at least 48 characters in production")
        if len(self.admin_jwt_secret) < 48:
            problems.append("ADMIN_JWT_SECRET must be at least 48 characters in production")
        if "sslmode=" not in self.database_url or "sslmode=disable" in self.database_url:
            problems.append("DATABASE_URL must set sslmode=require (or verify-full) in production")
        if self.s3_endpoint_url and not self.s3_endpoint_url.startswith("https://"):
            problems.append("S3_ENDPOINT_URL must be https in production")
        for origin in self.cors_origin_list:
            if not origin.startswith("https://"):
                problems.append(f"CORS_ORIGINS entry is not https: {origin}")
        if self.expose_docs:
            problems.append("EXPOSE_DOCS must be false in production")
        # Without a mail sender nobody can ever verify an address, so password
        # accounts stay half-created and Google sign-in cannot link to them.
        if not self.smtp_host:
            problems.append("SMTP_HOST must be set in production to send verification email")
        if not self.mail_from:
            problems.append("MAIL_FROM must be set in production")
        if bool(self.smtp_username) != bool(self.smtp_password):
            problems.append("SMTP_USERNAME and SMTP_PASSWORD must be set together")
        # Staff have no password to fall back on: without a client id there is no
        # way to reach the admin panel, and without mail there is no way past it.
        if not self.google_client_id:
            problems.append(
                "GOOGLE_CLIENT_ID must be set in production - it is the only staff sign-in"
            )
        if self.verify_link_base.startswith("http://"):
            problems.append("VERIFY_LINK_BASE must be https in production - it carries a token")
        if problems:
            raise ValueError("unsafe production configuration: " + "; ".join(problems))
        return self


settings = Settings()
