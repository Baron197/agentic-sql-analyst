import psycopg
import pytest

from sql_analyst.config import get_settings
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.safety.executor import Executor
from sql_analyst.safety.scope import UserScope

JABODETABEK = [1, 2, 3, 4, 5]  # Jakarta, Bogor, Depok, Tangerang, Bekasi
ANALYST = UserScope(user_id="analyst@demo", role="analyst", region_ids="all")
MANAGER = UserScope(user_id="manager.jakarta@demo", role="manager", region_ids=JABODETABEK)


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def executor(settings):
    with Executor.from_settings(settings, load_dictionary()) as ex:
        yield ex


@pytest.fixture
def reader_conn(settings):
    """A raw connection as nlq_reader: bypasses the validator and the executor."""
    with psycopg.connect(settings.reader_conninfo()) as conn:
        yield conn


@pytest.fixture
def admin_conn(settings):
    with psycopg.connect(settings.admin_conninfo()) as conn:
        yield conn
