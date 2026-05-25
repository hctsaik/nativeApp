"""
seed_data.py — Seed 5 AOI tasks into iwsc_tasks if the table is empty.
"""

import json
from datetime import datetime, timezone

from database import get_connection

SEED_TASKS = [
    {
        "ant_id": "IWSC-2026-001",
        "ant_period": "2026-05-26T08:00:00Z",
        "external_context": {
            "lot_id": "L001",
            "eqp_id": "AOI-A3",
            "recipe": "DRAM_256G",
        },
    },
    {
        "ant_id": "IWSC-2026-002",
        "ant_period": "2026-05-27T08:00:00Z",
        "external_context": {
            "lot_id": "L002",
            "eqp_id": "AOI-B1",
            "recipe": "NAND_512G",
        },
    },
    {
        "ant_id": "IWSC-2026-003",
        "ant_period": "2026-05-28T08:00:00Z",
        "external_context": {
            "lot_id": "L003",
            "eqp_id": "AOI-A3",
            "recipe": "DRAM_256G",
        },
    },
    {
        "ant_id": "IWSC-2026-004",
        "ant_period": "2026-05-29T08:00:00Z",
        "external_context": {
            "lot_id": "L004",
            "eqp_id": "AOI-B1",
            "recipe": "NAND_512G",
        },
    },
    {
        "ant_id": "IWSC-2026-005",
        "ant_period": "2026-05-30T08:00:00Z",
        "external_context": {
            "lot_id": "L005",
            "eqp_id": "AOI-A3",
            "recipe": "DRAM_256G",
        },
    },
]


def seed_if_empty() -> None:
    """Insert seed tasks only when the table contains no rows."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) FROM iwsc_tasks").fetchone()
        if row[0] > 0:
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for task in SEED_TASKS:
            conn.execute(
                """
                INSERT INTO iwsc_tasks
                    (ant_id, ant_period, external_context, ant_active, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (
                    task["ant_id"],
                    task["ant_period"],
                    json.dumps(task["external_context"]),
                    now,
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()
