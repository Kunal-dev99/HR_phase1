"""Application settings (BE-0.2).

Settings are read from the environment and from ``backend/.env``. Defaults preserve the
current behaviour (D-02): authentication is disabled (every non-public route returns 401),
the screening-run feature is off, and no HR System adapter is configured.

Startup validation fails closed: a production environment refuses development-only
authentication (``AUTH_MODE=dev_header``) and the mock HR System adapter.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    DISABLED = "disabled"
    DEV_HEADER = "dev_header"


MOCK_HR_SYSTEM_ADAPTER = "mock"

# backend/.env, independent of the current working directory.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class UnsafeConfigurationError(ValueError):
    """Raised when the configuration is not allowed for the environment."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=True,
    )

    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DATABASE_URL: str = Field(min_length=1)
    AUTH_MODE: AuthMode = AuthMode.DISABLED
    FEATURE_SCREENING_RUNS: bool = False
    HR_SYSTEM_ADAPTER: str | None = None

    @model_validator(mode="after")
    def _fail_closed_in_production(self) -> Settings:
        ensure_safe_configuration(self)
        return self


def unsafe_configuration_reasons(settings: Settings) -> list[str]:
    """Return every reason the configuration is unsafe for its environment."""
    reasons: list[str] = []
    if settings.ENVIRONMENT is Environment.PRODUCTION:
        if settings.AUTH_MODE is AuthMode.DEV_HEADER:
            reasons.append("AUTH_MODE=dev_header is not allowed when ENVIRONMENT=production")
        adapter = (settings.HR_SYSTEM_ADAPTER or "").strip().lower()
        if adapter == MOCK_HR_SYSTEM_ADAPTER:
            reasons.append("HR_SYSTEM_ADAPTER=mock is not allowed when ENVIRONMENT=production")
    return reasons


def ensure_safe_configuration(settings: Settings) -> None:
    """Raise ``UnsafeConfigurationError`` if the configuration must not start."""
    reasons = unsafe_configuration_reasons(settings)
    if reasons:
        raise UnsafeConfigurationError("; ".join(reasons))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # values come from the environment and backend/.env
