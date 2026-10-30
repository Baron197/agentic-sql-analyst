"""Demo users and their data scopes. Phase 5 adds sign-in; the scopes stay the same."""

from sql_analyst.safety.scope import UserScope

# Region ids 1-5 are Jabodetabek (Jakarta, Bogor, Depok, Tangerang, Bekasi); see docs/DATA.md.
DEMO_USERS: dict[str, UserScope] = {
    "analyst": UserScope(user_id="analyst@demo", role="analyst", region_ids="all"),
    "manager_jakarta": UserScope(
        user_id="manager.jakarta@demo", role="manager", region_ids=[1, 2, 3, 4, 5]
    ),
}
