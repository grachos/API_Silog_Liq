"""Application configuration and environment settings."""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables and/or .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Project metadata
    PROJECT_NAME: str = "API Silogtran Liquidaciones"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "production"

    # Silogtran Credentials & URLs
    SILOGTRAN_BASE_URL: str = Field(
        default="https://construproyec.colombiasoftware.net",
        description="Base URL of the Silogtran installation"
    )
    SILOGTRAN_LOGIN_URL: str = Field(
        default="https://construproyec.colombiasoftware.net/index.php?page=Login",
        description="Login page URL for Silogtran"
    )
    SILOGTRAN_REPORT_URL: str = Field(
        default="https://construproyec.colombiasoftware.net/index.php?page=Despacho.Liquidacionmanifiesto.InformeGeneral_111",
        description="Report URL for Liquidación de Manifiestos"
    )
    SILOGTRAN_USERNAME: str = Field(
        default="",
        description="Silogtran login username"
    )
    SILOGTRAN_PASSWORD: str = Field(
        default="",
        description="Silogtran login password"
    )
    SILOGTRAN_COST_CENTER: str = Field(
        default="CONSTRUPROYEC-PRINCIPAL",
        description="Mandatory cost center to select after login"
    )

    # PRADO Form field overrides (optional adaptors if Silogtran changes input IDs)
    SILOGTRAN_USER_FIELD: Optional[str] = None
    SILOGTRAN_PASS_FIELD: Optional[str] = None
    SILOGTRAN_COST_CENTER_FIELD: Optional[str] = None
    SILOGTRAN_DATE_START_FIELD: Optional[str] = None
    SILOGTRAN_DATE_END_FIELD: Optional[str] = None
    SILOGTRAN_PRINT_TYPE_FIELD: Optional[str] = None
    SILOGTRAN_PRINT_TYPE: Optional[str] = Field(
        default=None,
        description="Text or value of the 'Tipo de Impresión' option to pick (auto-detects CSV/Excel/HTML if empty)"
    )

    # Consumer Authentication
    API_TOKEN: Optional[str] = Field(
        default=None,
        description="Static permanent Bearer token for single consumer setups"
    )
    ADMIN_API_KEY: Optional[str] = Field(
        default=None,
        description="Secret key to manage consumer tokens via admin endpoints"
    )
    TOKEN_STORAGE_PATH: str = Field(
        default="tokens.json",
        description="Path to json file used for persistent token storage"
    )

    # Cache & Memory Management
    CACHE_TTL_SECONDS: int = Field(
        default=900,
        description="Cache TTL in seconds (15 minutes default)"
    )
    MAX_CACHE_ENTRIES: int = Field(
        default=500,
        description="Maximum entries in LRU cache to respect 512MB RAM"
    )

    # Request limits & validation
    MAX_DATE_RANGE_DAYS: int = Field(
        default=31,
        description="Maximum date range allowed per query"
    )
    REQUEST_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        description="HTTP client timeout in seconds for Silogtran requests"
    )
    SILOGTRAN_SESSION_LIFETIME_SECONDS: int = Field(
        default=900,
        description="Estimated lifetime of Silogtran session cookie before forced renewal"
    )

    # Rate Limiting & Security
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=60,
        description="Max requests per minute per consumer token or IP"
    )
    CORS_ORIGINS: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins"
    )

    # Server & Logging
    PORT: int = Field(default=8000, description="Server port")
    LOG_LEVEL: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")


settings = Settings()
