import itertools
import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://seatlock:seatlock@localhost:55440/splitkit_test"
)
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes-long"
os.environ["BCRYPT_ROUNDS"] = "4"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import create_app  # noqa: E402

_ids = itertools.count(1)


@pytest.fixture(scope="session")
def app():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return create_app()


@pytest.fixture(autouse=True)
def clean_db(app):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def make_user(app):
    """make_user("Asha") -> a TestClient signed in as a new user, with .id and .email."""

    def make(name: str = "User") -> TestClient:
        client = TestClient(app)
        email = f"{name.lower()}{next(_ids)}@test.dev"
        res = client.post(
            "/api/auth/signup", json={"email": email, "name": name, "password": "password123"}
        )
        assert res.status_code == 201, res.text
        client.id = res.json()["user"]["id"]  # type: ignore[attr-defined]
        client.email = email  # type: ignore[attr-defined]
        return client

    return make


@pytest.fixture
def anon(app):
    return TestClient(app)
