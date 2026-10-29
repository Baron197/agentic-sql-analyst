from psycopg.conninfo import conninfo_to_dict

from sql_analyst.config import Settings


def test_admin_conninfo_uses_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "db.example")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DB", "testdb")
    monkeypatch.setenv("POSTGRES_USER", "owner")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss word")

    settings = Settings(_env_file=None)
    parts = conninfo_to_dict(settings.admin_conninfo())

    assert parts == {
        "host": "db.example",
        "port": "6543",
        "dbname": "testdb",
        "user": "owner",
        "password": "p@ss word",
    }


def test_password_is_hidden_in_repr(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "hunter2")
    assert "hunter2" not in repr(Settings(_env_file=None))
