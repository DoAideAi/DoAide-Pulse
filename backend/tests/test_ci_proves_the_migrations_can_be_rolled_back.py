"""CI runs every migration down as well as up, on PostgreSQL.

``rollback.sh --db-only <rev>`` is the documented way back from a migration
that went wrong, and it runs ``alembic downgrade``. CI only ever ran
``alembic upgrade head``, so no downgrade had been executed on PostgreSQL by
anything: the first time one ran would be during the incident it exists for,
and a downgrade that raised then would leave the database half way between
two revisions with the old code waiting to start against it.

The backend job now migrates a fresh database to head, all the way down to
base, and back up to head, on the same Postgres service as before.
"""
from __future__ import annotations

from pathlib import Path

import yaml

CI = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _backend_steps() -> list[dict]:
    workflow = yaml.safe_load(CI.read_text())
    return workflow["jobs"]["backend"]["steps"]


def _runs() -> list[tuple[str, str, dict]]:
    return [
        (step.get("name", ""), str(step.get("run", "")), step.get("env") or {})
        for step in _backend_steps()
    ]


def test_the_chain_goes_down_to_base_and_back_up():
    commands = " ".join(run for _, run, _ in _runs())
    up = commands.index("alembic upgrade head")
    down = commands.index("alembic downgrade base")
    assert up < down < commands.index("alembic upgrade head", down)


def test_the_round_trip_runs_on_postgres():
    for name, run, env in _runs():
        if "alembic downgrade base" in run:
            assert env.get("DATABASE_URL", "").startswith("postgresql"), name
            return
    raise AssertionError("no step runs alembic downgrade base")
