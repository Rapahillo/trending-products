import pytest


@pytest.fixture(autouse=True)
def setup_db():
    """Override the root conftest setup_db to avoid DB connections in unit tests."""
    yield
