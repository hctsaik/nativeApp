from __future__ import annotations

import base64
import os
import sqlite3
from pathlib import Path


def _db_path() -> Path:
    return Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "edge_records.sqlite"


_OPTIONAL_COLUMNS = (
    "gradient_dir_variance",
    "psd_energy_ratio",
    "fit_overall",
    "fit_offset_score",
    "fit_left",
    "fit_right",
    "fit_avg_dist",
    "fit_avg_signed_dist",
    "fit_left_dist",
    "fit_right_dist",
    "fit_left_signed_dist",
    "fit_right_signed_dist",
)


def _select_expr(existing: set[str], column: str) -> str:
    if column in existing:
        return column
    return f"NULL AS {column}"


def execute_logic(params: dict) -> dict:
    date_from: str = str(params.get("date_from", "")).strip()
    date_to:   str = str(params.get("date_to", "")).strip()

    if not date_from or not date_to:
        return {"date_from": date_from, "date_to": date_to, "records": [], "error": "no_date"}

    db = _db_path()
    if not db.exists():
        return {"date_from": date_from, "date_to": date_to, "records": [], "error": "no_db"}

    parts_filter:    list[str] = params.get("parts", []) or []
    image_name_kw:   str       = params.get("image_name_kw", "")
    left_min:  float = float(params.get("left_min",  0.0))
    left_max:  float = float(params.get("left_max",  9999.0))
    right_min: float = float(params.get("right_min", 0.0))
    right_max: float = float(params.get("right_max", 9999.0))

    conditions = ["DATE(timestamp) BETWEEN ? AND ?"]
    args: list = [date_from, date_to]

    if parts_filter:
        placeholders = ",".join("?" * len(parts_filter))
        conditions.append(f"parts IN ({placeholders})")
        args.extend(parts_filter)

    if image_name_kw:
        conditions.append("image_name LIKE ?")
        args.append(f"%{image_name_kw}%")

    conditions.append("left_roughness  BETWEEN ? AND ?")
    args.extend([left_min, left_max])

    conditions.append("right_roughness BETWEEN ? AND ?")
    args.extend([right_min, right_max])

    where = " AND ".join(conditions)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        existing = {r[1] for r in conn.execute("PRAGMA table_info(edge_records)").fetchall()}
        optional_select = ",\n                   ".join(
            _select_expr(existing, col) for col in _OPTIONAL_COLUMNS
        )
        rows = conn.execute(
            f"""
            SELECT id, parts, image_name,
                   left_roughness, right_roughness,
                   frequency, intensity,
                   image_width, image_height,
                   timestamp, image_blob,
                   {optional_select}
            FROM edge_records
            WHERE {where}
            ORDER BY timestamp DESC
            """,  # noqa: S608
            args,
        ).fetchall()

    records = []
    for row in rows:
        blob: bytes | None = row["image_blob"]
        records.append(
            {
                "id":                    row["id"],
                "parts":                 row["parts"] or "",
                "image_name":            row["image_name"] or "",
                "left_roughness":        row["left_roughness"],
                "right_roughness":       row["right_roughness"],
                "frequency":             row["frequency"],
                "intensity":             row["intensity"],
                "image_width":           row["image_width"],
                "image_height":          row["image_height"],
                "timestamp":             row["timestamp"],
                "image_b64":             base64.b64encode(blob).decode("ascii") if blob else None,
                "gradient_dir_variance": row["gradient_dir_variance"],
                "psd_energy_ratio":      row["psd_energy_ratio"],
                "fit_overall":           row["fit_overall"],
                "fit_offset_score":      row["fit_offset_score"],
                "fit_left":              row["fit_left"],
                "fit_right":             row["fit_right"],
                "fit_avg_dist":          row["fit_avg_dist"],
                "fit_avg_signed_dist":   row["fit_avg_signed_dist"],
                "fit_left_dist":         row["fit_left_dist"],
                "fit_right_dist":        row["fit_right_dist"],
                "fit_left_signed_dist":  row["fit_left_signed_dist"],
                "fit_right_signed_dist": row["fit_right_signed_dist"],
            }
        )

    return {
        "date_from": date_from,
        "date_to":   date_to,
        "records":   records,
        "filters":   {
            "parts":        parts_filter,
            "image_name_kw": image_name_kw,
            "left_min":     left_min,
            "left_max":     left_max,
            "right_min":    right_min,
            "right_max":    right_max,
        },
    }
