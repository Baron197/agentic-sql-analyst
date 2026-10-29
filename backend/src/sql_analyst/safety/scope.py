"""Who is asking, and which regions they may see.

The executor calls `apply_scope` at the start of every transaction. It sets
`app.region_ids` plus an HMAC signature bound to this backend and transaction;
the row-level security policies (db/security.sql) ignore any scope whose signature
does not verify, so SQL cannot widen its own scope with set_config().
"""

import hashlib
import hmac
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

ALL_REGIONS = "all"


class UserScope(BaseModel):
    """The signed-in user's identity and data scope. Comes from auth, never from the model."""

    user_id: str
    role: Literal["analyst", "manager"]
    region_ids: list[int] | Literal["all"] = Field(min_length=1)

    def scope_text(self) -> str:
        if self.region_ids == ALL_REGIONS:
            return ALL_REGIONS
        return ",".join(str(r) for r in sorted({int(r) for r in self.region_ids}))


def sign(scope_text: str, backend_pid: int, xact_start_us: int, key: bytes) -> str:
    message = f"{scope_text}|{backend_pid}|{xact_start_us}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def apply_scope(conn: psycopg.Connection, scope: UserScope, key: bytes) -> None:
    """Set the signed region scope for the current transaction (must not be autocommit)."""
    if conn.autocommit:
        raise RuntimeError("apply_scope needs a transaction; the scope is SET LOCAL")
    text = scope.scope_text()
    pid, xact_us = conn.execute(
        "SELECT pg_backend_pid(), floor(extract(epoch FROM transaction_timestamp()) * 1000000)::bigint"
    ).fetchone()
    conn.execute(
        "SELECT set_config('app.region_ids', %s, true), set_config('app.region_sig', %s, true)",
        (text, sign(text, pid, xact_us, key)),
    )
