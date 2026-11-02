"""GET /api/schema, GET /api/examples, and GET /api/recorded-runs (public)."""

from typing import Any

from fastapi import APIRouter

from sql_analyst import recorded
from sql_analyst.agent.keyless import load_demo
from sql_analyst.api.auth import CurrentUser, Res
from sql_analyst.users import DEMO_USERS

router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/schema")
def schema(user: CurrentUser, res: Res) -> dict[str, Any]:
    """The data dictionary, without columns flagged as personal data, plus the user's scope."""
    d = res.agent.deps.dictionary
    return {
        "company": d.company,
        "fictional": True,
        "data_window": d.data_window.model_dump(mode="json"),
        "your_scope": {"role": user.role, "region_ids": user.region_ids or "all"},
        "business_rules": d.business_rules,
        "views": [
            {
                "name": v.name,
                "description": v.description,
                "grain": v.grain,
                "columns": [
                    {
                        "name": c.name,
                        "type": c.type,
                        "description": c.description,
                        "examples": c.examples,
                        "deprecated": c.deprecated,
                    }
                    for c in v.columns
                    if not c.pii
                ],
            }
            for v in d.views
        ],
        "glossary": [
            {"name": m.name, "label": m.label.model_dump(), "description": m.description}
            for m in d.glossary
        ],
    }


@router.get("/examples")
def examples(user: CurrentUser, res: Res) -> dict[str, Any]:
    """Sample questions for the user's role; in keyless mode these are the ones it can answer."""
    keys = [k for k, scope in DEMO_USERS.items() if scope.user_id == user.user_id]
    demos = [d for d in load_demo() if not keys or keys[0] in d.users]
    return {
        "keyless": not res.live,
        "examples": [{"question": d.question, "lang": d.lang} for d in demos],
    }


@router.get("/recorded-runs", response_model=recorded.RecordedRuns)
def recorded_runs() -> recorded.RecordedRuns:
    """Real live-model runs recorded in the app and published (public, no sign-in; D048)."""
    return recorded.load()
