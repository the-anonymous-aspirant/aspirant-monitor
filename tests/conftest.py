from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_docker():
    with patch("app.routes._get_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        yield mock_client
