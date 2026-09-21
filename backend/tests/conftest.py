import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import client, ensure_indexes, get_db
from app.db.repositories.platform_repo import PlatformRepository
from app.main import app

TEST_DB_NAME = "pod_evaluator_test"


@pytest.fixture
def db_session():
    test_db = client[TEST_DB_NAME]
    client.drop_database(TEST_DB_NAME)
    ensure_indexes(test_db)
    PlatformRepository(test_db).get_or_create("tiki", "Tiki")
    yield test_db
    client.drop_database(TEST_DB_NAME)


@pytest.fixture
def client_app(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
