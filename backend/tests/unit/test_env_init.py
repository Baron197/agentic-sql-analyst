"""`poe env-init`: a local .env that works keyless, from the real .env.example."""

import shutil
from pathlib import Path

import pytest

from sql_analyst.config import Settings
from sql_analyst.env_init import SECRETS, render, write_env

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / ".env.example"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    shutil.copy(EXAMPLE, tmp_path / ".env.example")
    return tmp_path


@pytest.fixture
def clean_env(monkeypatch):
    """The test process's own env vars would override the file's values."""
    for key in [*SECRETS, "LLM_PROVIDER", "DEMO_LOGIN_ENABLED", "LIVE_MODE_ENABLED"]:
        monkeypatch.delenv(key, raising=False)


def test_written_env_is_valid_and_keyless(repo, clean_env):
    assert write_env(repo)
    settings = Settings(_env_file=repo / ".env")

    assert len(settings.signing_key()) >= 32  # hex, 32 bytes
    assert len(settings.jwt_secret.get_secret_value()) >= 32
    for field in ("postgres_password", "nlq_reader_password", "app_writer_password"):
        assert len(getattr(settings, field).get_secret_value()) >= 16
    assert settings.llm_provider == "fake"
    assert settings.demo_login_enabled is True
    assert settings.live_mode_enabled is False


def test_keeps_an_existing_env(repo):
    (repo / ".env").write_text("MINE=1\n", encoding="utf-8")
    assert not write_env(repo)
    assert (repo / ".env").read_text(encoding="utf-8") == "MINE=1\n"


def test_secrets_are_random_and_comments_kept():
    template = EXAMPLE.read_text(encoding="utf-8")
    a, b = render(template), render(template)
    assert a != b
    assert [ln for ln in a.splitlines() if ln.startswith("#")] == [
        ln for ln in template.splitlines() if ln.startswith("#")
    ]


def test_every_empty_secret_in_the_template_is_filled():
    """A new secret added to .env.example must be added to env_init too."""
    keys = {"PASSWORD", "SECRET", "SIGNING_KEY"}
    empty = {
        line.split("=", 1)[0]
        for line in EXAMPLE.read_text(encoding="utf-8").splitlines()
        if line.endswith("=") and not line.startswith("#")
    }
    secret_like = {k for k in empty if any(word in k for word in keys)}
    assert secret_like <= set(SECRETS)


def test_template_without_a_secret_is_an_error():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        render("POSTGRES_PASSWORD=\n")
