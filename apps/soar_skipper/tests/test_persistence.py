"""Persistence smoke test: confirm playbooks and runs survive a service
"restart" by pointing two store instances at the same on-disk SQLite file.
Before the SQL migration soar_skipper kept everything in process-level
dicts; this regression test guards against a silent revert.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.store import SoarStore


def test_playbooks_survive_simulated_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "soar.db"
    url = f"sqlite+pysqlite:///{db_path}"

    first = SoarStore(database_url=url)
    first.save_playbook(
        "pb_custom",
        {
            "id": "pb_custom",
            "name": "Custom",
            "enabled": False,
            "nodes": [{"id": "trigger", "type": "trigger.incident_created", "config": {}}],
            "edges": [],
        },
    )

    second = SoarStore(database_url=url)
    payload = second.get_playbook("pb_custom")

    assert payload is not None
    assert payload["name"] == "Custom"


def test_runs_survive_simulated_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "soar.db"
    url = f"sqlite+pysqlite:///{db_path}"

    first = SoarStore(database_url=url)
    created = datetime.now(UTC)
    first.save_run(
        {
            "id": "run_42",
            "incidentId": "inc_1",
            "playbookId": "pb_x",
            "dryRun": True,
            "status": "waiting_approval",
            "steps": [],
            "createdAt": created.isoformat(),
        },
        incident_id="inc_1",
        playbook_id="pb_x",
        status="waiting_approval",
        created_at=created,
    )

    second = SoarStore(database_url=url)
    payload = second.get_run("run_42")

    assert payload is not None
    assert payload["status"] == "waiting_approval"
    assert payload["playbookId"] == "pb_x"


def test_list_runs_filters_by_status(tmp_path: Path) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'soar.db'}"
    store = SoarStore(database_url=url)
    now = datetime.now(UTC)

    for run_id, status_value in [("run_a", "waiting_approval"), ("run_b", "completed")]:
        store.save_run(
            {
                "id": run_id,
                "incidentId": "inc_1",
                "playbookId": "pb_x",
                "dryRun": True,
                "status": status_value,
                "steps": [],
                "createdAt": now.isoformat(),
            },
            incident_id="inc_1",
            playbook_id="pb_x",
            status=status_value,
            created_at=now,
        )

    completed = store.list_runs(status="completed")
    assert [r["id"] for r in completed] == ["run_b"]

    waiting = store.list_runs(status="waiting_approval")
    assert [r["id"] for r in waiting] == ["run_a"]

    everything = store.list_runs()
    assert {r["id"] for r in everything} == {"run_a", "run_b"}
