import pytest

from sql_analyst.config import get_settings
from sql_analyst.db.ping import ping

pytestmark = pytest.mark.db


def test_ping_reports_version_and_pgvector():
    result = ping(get_settings())
    assert result.server_version.startswith("16")
    assert result.vector_available
