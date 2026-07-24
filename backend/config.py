"""
Central configuration loaded from .env via Pydantic BaseSettings.
All other modules import from here — never read os.environ directly.
"""

from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    database_url: str = Field(description="Async PostgreSQL URL loaded from .env")
    database_url_sync: str = Field(description="Sync PostgreSQL URL loaded from .env")

    # --- Application ---
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)
    debug: bool = Field(default=False, validation_alias="PRICEWATCH_DEBUG")
    log_level: str = Field(default="INFO")

    # --- Scheduler ---
    scheduler_timezone: str = Field(default="Europe/Berlin")

    # --- Scraping ---
    scraper_min_delay_seconds: float = Field(default=3.0)
    scraper_max_delay_seconds: float = Field(default=9.0)
    playwright_headless: bool = Field(default=True)

    # --- Screenshots ---
    screenshot_dir: Path = Field(default=Path("./screenshots"))

    # --- AI ---
    anthropic_api_key: str = Field(default="")
    researcher_model: str = Field(default="claude-sonnet-4-6")

    # --- Security ---
    api_key: str = Field(description="Secret key required in X-API-Key header for all API calls")

    # --- Frontend ---
    frontend_url: str = Field(default="http://localhost:3000")

    @field_validator("screenshot_dir", mode="before")
    @classmethod
    def resolve_screenshot_dir(cls, v: str | Path) -> Path:
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @model_validator(mode="after")
    def reject_unsafe_runtime_secrets(self):
        key = self.api_key.strip()
        if len(key) < 32 or key in {"change-me-before-use", "pricewatch_secret"}:
            raise ValueError("API_KEY must be a generated secret with at least 32 characters")
        for name, value in (
            ("DATABASE_URL", self.database_url),
            ("DATABASE_URL_SYNC", self.database_url_sync),
        ):
            if "pricewatch_secret" in value or "change-me-before-use" in value:
                raise ValueError(f"{name} contains a repository-known placeholder")
        if self.app_host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("APP_HOST must be loopback; PriceWatch is a local application")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
