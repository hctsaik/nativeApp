"""Domain services for the bi plugin.

Keep business logic here (pure, testable), separate from Streamlit UI. Modules
under modules/ import and call these. Mirrors plugins/labeling/domain/services.py.
"""
from __future__ import annotations


class BiService:
    """Entry point for bi domain operations."""

    def ping(self) -> str:
        return "bi domain ready"
