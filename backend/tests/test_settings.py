import pytest
from pydantic import SecretStr, ValidationError

from app.core.settings import (
    AuthMode,
    Environment,
    Settings,
    UnsafeConfigurationError,
    ensure_safe_configuration,
)
from app.main import create_app

URL = "postgresql+asyncpg://u:p@localhost:5432/hr_phase1_p1req_copy"


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, DATABASE_URL=URL, **overrides)  # type: ignore[arg-type]


def test_defaults_preserve_current_behaviour() -> None:
    s = _settings()
    assert s.AUTH_MODE is AuthMode.DISABLED
    assert s.FEATURE_SCREENING_RUNS is False
    assert s.HR_SYSTEM_ADAPTER is None


def test_production_rejects_dev_auth_and_mock_adapter() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=dev_header"):
        _settings(ENVIRONMENT="production", AUTH_MODE="dev_header")
    with pytest.raises(ValidationError, match="HR_SYSTEM_ADAPTER=mock"):
        _settings(ENVIRONMENT="production", HR_SYSTEM_ADAPTER="mock")
    with pytest.raises(ValidationError, match="HR_SYSTEM_ADAPTER=mock"):
        _settings(ENVIRONMENT="production", HR_SYSTEM_ADAPTER=" MOCK ")

    # The app factory refuses to start even if validation was bypassed.
    unsafe = Settings.model_construct(
        ENVIRONMENT=Environment.PRODUCTION,
        DATABASE_URL=URL,
        AUTH_MODE=AuthMode.DEV_HEADER,
        FEATURE_SCREENING_RUNS=False,
        HR_SYSTEM_ADAPTER="mock",
    )
    with pytest.raises(ValueError, match="not allowed when ENVIRONMENT=production"):
        create_app(unsafe)

    # The same settings are allowed outside production.
    assert _settings(AUTH_MODE="dev_header", HR_SYSTEM_ADAPTER="mock").AUTH_MODE is (
        AuthMode.DEV_HEADER
    )
    # Production with safe defaults starts.
    create_app(_settings(ENVIRONMENT="production"))


def test_role_brief_requires_ai_provider_and_key() -> None:
    def construct(**overrides: object) -> Settings:
        base: dict[str, object] = {
            "ENVIRONMENT": Environment.DEVELOPMENT,
            "DATABASE_URL": URL,
            "AUTH_MODE": AuthMode.DISABLED,
            "FEATURE_SCREENING_RUNS": True,
            "HR_SYSTEM_ADAPTER": "mock",
            "FEATURE_ROLE_BRIEF": True,
            "AI_PROVIDER": None,
            "GROQ_API_KEY": None,
        }
        return Settings.model_construct(**{**base, **overrides})  # type: ignore[arg-type]

    with pytest.raises(UnsafeConfigurationError, match="requires AI_PROVIDER"):
        ensure_safe_configuration(construct())
    with pytest.raises(UnsafeConfigurationError, match="requires GROQ_API_KEY"):
        ensure_safe_configuration(construct(AI_PROVIDER="groq"))
    with pytest.raises(UnsafeConfigurationError, match="requires GROQ_API_KEY"):
        ensure_safe_configuration(construct(AI_PROVIDER="groq", GROQ_API_KEY=SecretStr(" ")))
    # The mock provider is accepted outside production.
    ensure_safe_configuration(construct(AI_PROVIDER="mock"))
