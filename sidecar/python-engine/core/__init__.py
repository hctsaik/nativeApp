"""CIM platform core — infrastructure shared across all feature plugins.

This package is the single home for platform-level building blocks (external
system integration contracts, and over time DB/log/config/auth/plugin
machinery). The dependency rule is one-way: ``plugins/* -> core/*`` is allowed,
``core/* -> plugins/*`` is forbidden (see tests/test_architecture_boundaries.py).

See docs/platform/shared-components.md for the discoverability index and
docs/platform/architecture-restructure-discussion.md for the roadmap.
"""
