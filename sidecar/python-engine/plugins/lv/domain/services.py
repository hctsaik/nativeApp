"""Domain services for the lv plugin.

Thin by design: LV is a self-contained Streamlit app run via tools/lv_runner.py,
so platform-side domain logic is minimal. Mirrors plugins/bi/domain/services.py;
this is where any future host-side glue (e.g. handing annotation outputs to LV)
would live, kept pure and testable, separate from Streamlit UI.
"""
from __future__ import annotations


class LvService:
    """Entry point for lv domain operations."""

    def ping(self) -> str:
        return "lv domain ready"
