import os
import pytest

@pytest.fixture(scope="session", autouse=True)
def isolated_data(tmp_path_factory):
    root=tmp_path_factory.mktemp("theo-tests")
    os.environ["THEO_DATA_DIR"]=str(root)
    os.environ["DATABASE_URL"]=f"sqlite:///{root/'test.db'}"
    os.environ["MAX_UPLOAD_MB"]="5"
    yield

@pytest.fixture(scope="session")
def client(isolated_data):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
