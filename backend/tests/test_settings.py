import pytest
from pydantic import ValidationError

from app.core.settings import AuthMode, Environment, Settings
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
