"""Write a local `.env` from `.env.example` with fresh random secrets: `uv run poe env-init`.

For a first local run: keyless (no model calls, no API key), with the one-click demo
sign-in turned on. Never overwrites an existing `.env` and never prints a secret.
"""

import contextlib
import re
import secrets
import sys
from pathlib import Path

# Each secret and how to make it. RLS_SIGNING_KEY must be hex (32 bytes); the rest are
# passwords or keys of at least 32 characters.
SECRETS = {
    "POSTGRES_PASSWORD": lambda: secrets.token_hex(24),
    "NLQ_READER_PASSWORD": lambda: secrets.token_hex(24),
    "RLS_SIGNING_KEY": lambda: secrets.token_hex(32),
    "APP_WRITER_PASSWORD": lambda: secrets.token_hex(24),
    "JWT_SECRET": lambda: secrets.token_hex(32),
    "DEMO_ANALYST_PASSWORD": lambda: secrets.token_hex(16),
    "DEMO_MANAGER_PASSWORD": lambda: secrets.token_hex(16),
}
# Local keyless defaults that differ from the template.
OVERRIDES = {"LLM_PROVIDER": "fake", "DEMO_LOGIN_ENABLED": "true"}

LINE = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>.*)$")


def render(template: str) -> str:
    """The template with every secret filled in and the local overrides applied."""
    out = []
    for line in template.splitlines():
        m = LINE.match(line)
        if m and m["key"] in SECRETS:
            line = f"{m['key']}={SECRETS[m['key']]()}"
        elif m and m["key"] in OVERRIDES:
            line = f"{m['key']}={OVERRIDES[m['key']]}"
        out.append(line)
    missing = set(SECRETS) - {m["key"] for line in out if (m := LINE.match(line))}
    if missing:
        raise ValueError(f".env.example is missing {sorted(missing)}")
    return "\n".join(out) + "\n"


def write_env(root: Path) -> bool:
    """Write `root/.env` unless it exists. Returns True if a file was written."""
    target = root / ".env"
    if target.exists():
        return False
    text = render((root / ".env.example").read_text(encoding="utf-8"))
    target.write_text(text, encoding="utf-8")
    with contextlib.suppress(OSError):
        target.chmod(0o600)  # owner-only where the filesystem supports it
    return True


def main() -> int:
    root = Path.cwd()
    if write_env(root):
        print("Wrote .env with random secrets: keyless mode, one-click demo sign-in on.")
    else:
        print(".env already exists; kept it unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
