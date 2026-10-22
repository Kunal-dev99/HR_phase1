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

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    DISABLED = "disabled"
    DEV_HEADER = "dev_header"


class RunExecutorKind(StrEnum):
    """How screening runs are executed after the request commits (D-06, BE-2.2)."""

    IN_PROCESS = "in_process"
    INLINE = "inline"


MOCK_HR_SYSTEM_ADAPTER = "mock"
MOCK_AI_PROVIDER = "mock"
GROQ_AI_PROVIDER = "groq"

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
    # Per-call timeout for HR System adapter calls (BE-1.4). One attempt, no retries (D-06).
    HR_SYSTEM_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=300)
    # HR System statuses that make a requisition eligible for screening (D-07, BE-1.6).
    # Set as JSON, e.g. REQUISITION_ELIGIBLE_SOURCE_STATUSES='["open"]'.
    REQUISITION_ELIGIBLE_SOURCE_STATUSES: tuple[str, ...] = ("open",)
    # Background execution of screening runs (D-06, BE-2.2).
    RUN_EXECUTOR: RunExecutorKind = RunExecutorKind.IN_PROCESS
    # Startup recovery blocks runs left in ingesting_requisition longer than this.
    INGESTION_STALE_AFTER_SECONDS: int = Field(default=600, gt=0)
    # Role brief generation (D-31, D-32, D-37). Off by default: runs stop at role_brief_draft.
    FEATURE_ROLE_BRIEF: bool = False
    # AI_PROVIDER: "mock" | "groq". Unset by default; "mock" is refused in production.
    AI_PROVIDER: str | None = None
    AI_MODEL: str = "openai/gpt-oss-120b"
    # Per-call timeout for AI calls. One attempt, no retries (D-06).
    AI_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0, le=300)
    # Read from the environment or the gitignored backend/.env only (D-31). SecretStr keeps
    # it out of repr, logs and error messages.
    GROQ_API_KEY: SecretStr | None = None
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    @model_validator(mode="after")
    def _fail_closed_in_production(self) -> Settings:
        ensure_safe_configuration(self)
        return self


def unsafe_configuration_reasons(settings: Settings) -> list[str]:
    """Return every reason the configuration is unsafe for its environment."""
    reasons: list[str] = []
    if settings.FEATURE_SCREENING_RUNS and not (settings.HR_SYSTEM_ADAPTER or "").strip():
        reasons.append("FEATURE_SCREENING_RUNS=true requires HR_SYSTEM_ADAPTER to be set")
    ai_provider = (settings.AI_PROVIDER or "").strip().lower()
    if settings.FEATURE_ROLE_BRIEF:
        if not settings.FEATURE_SCREENING_RUNS:
            reasons.append("FEATURE_ROLE_BRIEF=true requires FEATURE_SCREENING_RUNS=true")
        if not ai_provider:
            reasons.append("FEATURE_ROLE_BRIEF=true requires AI_PROVIDER to be set")
    if ai_provider == GROQ_AI_PROVIDER and (
        settings.GROQ_API_KEY is None or not settings.GROQ_API_KEY.get_secret_value().strip()
    ):
        reasons.append("AI_PROVIDER=groq requires GROQ_API_KEY to be set")
    if settings.ENVIRONMENT is Environment.PRODUCTION:
        if settings.AUTH_MODE is AuthMode.DEV_HEADER:
            reasons.append("AUTH_MODE=dev_header is not allowed when ENVIRONMENT=production")
        adapter = (settings.HR_SYSTEM_ADAPTER or "").strip().lower()
        if adapter == MOCK_HR_SYSTEM_ADAPTER:
            reasons.append("HR_SYSTEM_ADAPTER=mock is not allowed when ENVIRONMENT=production")
        if ai_provider == MOCK_AI_PROVIDER:
            reasons.append("AI_PROVIDER=mock is not allowed when ENVIRONMENT=production")
    return reasons


def ensure_safe_configuration(settings: Settings) -> None:
    """Raise ``UnsafeConfigurationError`` if the configuration must not start."""
    reasons = unsafe_configuration_reasons(settings)
    if reasons:
        raise UnsafeConfigurationError("; ".join(reasons))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # values come from the environment and backend/.env
