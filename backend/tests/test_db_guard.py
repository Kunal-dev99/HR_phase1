import pytest

from tests.db_guard import UnsafeTestDatabaseError, assert_copy_database


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@localhost:5432/hr_phase1",
        "postgresql+asyncpg://u:p@localhost:5432/hr_phase1_dev",
        "postgresql+asyncpg://u:p@localhost:5432/hr_phase1_copy_live",
        "postgresql+asyncpg://u:p@localhost:5432/hr_phase1_test2",
        "postgresql+asyncpg://u:p@localhost:5432/_copy",
        "postgresql+asyncpg://u:p@localhost:5432/",
        "postgresql+asyncpg://u:p@localhost:5432/hr_phase1?x=_copy",
        "not a url",
    ],
)
def test_refuses_non_copy_database(url: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_copy_database(url)


@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("postgresql+asyncpg://u:p@localhost:5432/hr_phase1_p1req_copy", "hr_phase1_p1req_copy"),
        ("postgresql+asyncpg://u:p@localhost/hr_phase1_p1req_test", "hr_phase1_p1req_test"),
    ],
)
def test_accepts_copy_database(url: str, name: str) -> None:
    assert assert_copy_database(url) == name
