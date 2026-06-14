from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel

from management_insights import validate_sheet_prod_readiness
from management_insights import validate_module_snapshot_content
from management_schema import SQLiteManagementSchema
from management_store import SQLiteManagementStore


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


ROOT_DIR = resource_root()
TOOLS_DIR = ROOT_DIR / "tools"


def resolve_tools_db_path(log_dir: Path | None = None) -> Path:
    env_path = os.environ.get("CIM_TOOLS_DB")
    if env_path:
        return Path(env_path).expanduser().resolve()
    if log_dir is not None:
        return (log_dir / "data" / "tools.sqlite").resolve()
    return (ROOT_DIR / "config" / "tools.sqlite").resolve()


_SEED_PATH = ROOT_DIR / "config" / "seed.yaml"


def _load_static_seed() -> dict:
    """Load the declarative static-catalog seed (config/seed.yaml).

    Holds tools that have no plugin.yaml (sheet runners / management / external)
    plus one-time migrations — the authoritative source replacing engine.py's
    old hardcoded INSERT tuples. Returns {} if the file or PyYAML is missing
    (engine still boots; plugin.yaml + sheet YAML remain the primary sources)."""
    try:
        import yaml
    except ImportError:
        logging.warning("PyYAML not available; skipping static seed (config/seed.yaml)")
        return {}
    if not _SEED_PATH.exists():
        logging.warning("config/seed.yaml not found at %s; no static seed applied", _SEED_PATH)
        return {}
    try:
        return yaml.safe_load(_SEED_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logging.error("Failed to parse config/seed.yaml: %s", exc)
        return {}


_BOOT_ID = uuid.uuid4().hex[:12]
_BOOTED_AT = datetime.now(timezone.utc).isoformat()
_GIT_COMMIT_CACHE: Optional[str] = None


def engine_commit() -> str:
    """Short git commit of the running engine code, so "am I running the fixed
    code, or a stale sidecar?" is answerable at a glance (the #1 reason a fix
    looked 'not working': the engine was never restarted on the new code).
    Cached per process. Falls back to a packaged BUILD_COMMIT file, then
    'unknown' (frozen build / source zip without git)."""
    global _GIT_COMMIT_CACHE
    if _GIT_COMMIT_CACHE is not None:
        return _GIT_COMMIT_CACHE
    commit = "unknown"
    try:
        build_file = ROOT_DIR / "BUILD_COMMIT"
        if build_file.exists():
            commit = build_file.read_text(encoding="utf-8").strip() or "unknown"
        else:
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(ROOT_DIR), capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                commit = out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    _GIT_COMMIT_CACHE = commit
    return commit


# Sentinel files that only exist once each external dependency's content is in
# place. Kept in sync with scripts/win/verify-setup.ps1 and preflight-submodules.bat.
# Two delivery modes (each entry's "kind"):
#   - "submodule" (AI4BI): content arrives via `git submodule update --init`.
#   - "external"  (Labeling): developed in its own repo (ANnoTation) and mounted
#     into plugins/labeling via a directory junction (scripts\win\link-labeling.bat).
# A missing sentinel means that content isn't there (GitHub "Download ZIP", a clone
# without --recurse-submodules, or the labeling junction not yet created). The
# plugin/sheet scans (which glob these dirs) then silently match nothing, so tools
# vanish from the catalog with NO error — these helpers turn that silent failure
# into a loud, pasteable [CIM-PREFLIGHT] signal.
_SUBMODULE_SENTINELS = (
    {
        "id": "labeling",
        "name": "影像標註 (Labeling)",
        "kind": "external",
        "submodule": "plugins/labeling",  # mount point (junction → repo: ANnoTation)
        "repo": "ANnoTation",
        "sentinel": ROOT_DIR / "plugins" / "labeling" / "plugin.manifest.yaml",
        "fix": "scripts\\win\\link-labeling.bat（先把 ANnoTation clone 到 nativeApp 旁）",
    },
    {
        "id": "ai4bi",
        "name": "AI Report (AI4BI)",
        "kind": "submodule",
        "submodule": "vendor/AI4BI",
        "repo": "AI4BI",
        "sentinel": ROOT_DIR / "vendor" / "AI4BI" / "ai4bi" / "ui" / "app.py",
        "fix": "git submodule update --init --recursive",
    },
    {
        "id": "lv",
        "name": "VisualLatent (LV)",
        "kind": "submodule",
        "submodule": "vendor/LV",
        "repo": "LV",
        "sentinel": ROOT_DIR / "vendor" / "LV" / "scripts" / "app.py",
        "fix": "git submodule update --init --recursive",
    },
)


def check_submodules() -> list[dict]:
    """Return descriptors for external deps whose content is missing.

    Empty list == all good. Each entry names the broken feature, where it should
    live and how to fix it (the fix differs by ``kind``: a git submodule update for
    AI4BI, the junction setup script for the external Labeling plugin), so the
    result is useful both for logging and for the /diagnostics endpoint (portal
    banner). Skipped in frozen/packaged builds, where this content is bundled
    differently and these paths don't apply.
    """
    if getattr(sys, "frozen", False):
        return []
    missing: list[dict] = []
    for sm in _SUBMODULE_SENTINELS:
        if not sm["sentinel"].exists():
            missing.append({
                "id": sm["id"],
                "name": sm["name"],
                "kind": sm.get("kind", "submodule"),
                "submodule": sm["submodule"],
                "repo": sm["repo"],
                "fix": sm.get("fix", "git submodule update --init --recursive"),
            })
    return missing


def preflight_submodules() -> list[dict]:
    """Log a loud, greppable, actionable error when submodule content is missing.

    Deliberately does NOT exit: the engine runs as an Electron-managed sidecar, so
    a hard exit would trigger main.js's crash→auto-restart loop. Instead we keep
    the engine alive (the app still partially works) and leave a clear trail in
    engine.log + /diagnostics. Grep [CIM-PREFLIGHT] to find / paste it to an AI.
    """
    missing = check_submodules()
    if not missing:
        return missing
    names = ", ".join(m["name"] for m in missing)
    logging.error("[CIM-PREFLIGHT] 缺少外掛內容：%s", names)
    logging.error("[CIM-PREFLIGHT] 症狀：工作流程清單會缺少這些項目，或點了無法啟動。")
    logging.error("[CIM-PREFLIGHT] 常見原因：用 GitHub「Download ZIP」、clone 沒加 "
                  "--recurse-submodules（AI4BI），或 labeling 的目錄 junction 尚未建立。")
    for m in missing:
        source = "外部外掛" if m.get("kind") == "external" else "submodule"
        logging.error("[CIM-PREFLIGHT]   - %s ← %s %s（repo: %s）→ 解法：%s",
                      m["name"], source, m["submodule"], m["repo"], m["fix"])
    logging.error("[CIM-PREFLIGHT] AI4BI 若用 ZIP 下載請改用 → "
                  "git clone --recurse-submodules https://github.com/hctsaik/nativeApp.git")
    return missing


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    name: str
    script_path: Path
    version: str
    signature: Optional[str] = None
    source_commit: Optional[str] = None
    author: Optional[str] = None
    approved_at: Optional[str] = None
    slug: Optional[str] = None


class SheetTabInfo(BaseModel):
    plugin_id: str
    label: str
    input_url: str
    output_url: str
    input_port: int
    output_port: int
    ready: bool = False


class ToolStartResponse(BaseModel):
    tool_id: str
    input_url: str
    output_url: str
    input_port: int
    output_port: int
    category: str = "module"
    sheet_tabs: list[SheetTabInfo] = []
    mode: str = "iframe"
    pid: Optional[int] = None
    run_id: Optional[str] = None
    ready: bool = False
    log_path: Optional[str] = None
    message: Optional[str] = None
    runtime: Optional[dict] = None


class ToolInfo(BaseModel):
    tool_id: str
    name: str
    version: str
    category: str = "tool"
    slug: Optional[str] = None


class SelectedPathsRequest(BaseModel):
    paths: list[str]


class SelectedPathsResponse(BaseModel):
    paths: list[str]


class ProdEnabledRequest(BaseModel):
    enabled: bool


class ToolAdapter(ABC):
    @abstractmethod
    def list_tools(self) -> list[ToolDefinition]:
        raise NotImplementedError

    @abstractmethod
    def get_tool(self, tool_id: str) -> ToolDefinition:
        raise NotImplementedError

    def rescan(self) -> dict:
        """Re-scan plugin/sheet YAML into the catalog (hot-reload). Default no-op."""
        return {"added": [], "total": len(self.list_tools())}


class MockToolAdapter(ToolAdapter):
    def __init__(self) -> None:
        self._tools = {
            "sample-csv": ToolDefinition(
                tool_id="sample-csv",
                name="Sample CSV Analyzer",
                script_path=TOOLS_DIR / "sample_csv_tool.py",
                version="0.1.0",
                signature=None,
                source_commit="mock",
                author="system",
                approved_at=None,
            )
        }

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_tool(self, tool_id: str) -> ToolDefinition:
        if tool_id not in self._tools:
            raise KeyError(tool_id)
        return self._tools[tool_id]


class SQLiteToolAdapter(ToolAdapter):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # Sheet tools auto-disabled by the orphan converge (see
        # _reconcile_sheets_from_yaml); surfaced via /diagnostics + boot log.
        self.orphan_sheets_disabled: list[str] = []
        SQLiteManagementSchema(self._db_path).ensure_current()
        self._store = SQLiteManagementStore(self._db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        """Build/upgrade the catalog DB. Behaviour-preserving phases (run every
        startup, all idempotent): create tables → one-time legacy migrations →
        scan plugin.yaml → seed static (sheet/management/external) tools →
        reconcile sheet YAML."""
        with self._connect() as connection:
            self._create_core_tables(connection)
            self._run_legacy_migrations(connection)
            self._scan_and_register_plugins(connection)   # plugin.yaml = source of truth
            self._seed_static_tools(connection)            # sheet/management/external (no plugin.yaml)
            self._reconcile_sheets_from_yaml(connection)

    def _create_core_tables(self, connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tools (
                tool_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                script_relative_path TEXT NOT NULL,
                version TEXT NOT NULL,
                signature TEXT,
                source_commit TEXT,
                author TEXT,
                approved_at TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                enabled_prod INTEGER NOT NULL DEFAULT 0,
                order_index INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Create tool_versions table (shared with plugin_registry)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_versions (
                version_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_id      TEXT NOT NULL,
                version      TEXT NOT NULL,
                content_json TEXT NOT NULL,
                changelog    TEXT,
                author       TEXT,
                created_at   TEXT DEFAULT (datetime('now')),
                is_active    INTEGER NOT NULL DEFAULT 0,
                source       TEXT NOT NULL DEFAULT 'filesystem'
            )
            """
        )

    def _run_legacy_migrations(self, connection) -> None:
        """One-time, idempotent migrations for old installs (no-op on fresh DBs).
        Each is guarded; new fresh installs simply match nothing."""
        # migration：舊 DB 補欄位
        for col_sql in [
            "ALTER TABLE tools ADD COLUMN enabled_prod INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tools ADD COLUMN order_index INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tools ADD COLUMN enabled_dev INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE tools ADD COLUMN description TEXT",
            "ALTER TABLE tools ADD COLUMN vendor TEXT DEFAULT 'cimcore'",
            "ALTER TABLE tools ADD COLUMN domain TEXT",
            "ALTER TABLE tools ADD COLUMN legacy_id TEXT",
            "ALTER TABLE tools ADD COLUMN deprecated_at TEXT",
        ]:
            try:
                connection.execute(col_sql)
            except Exception:
                pass
        # migration：cvmod-* → module_* (one-time rename)
        for old_id, new_id in [
            ("cvmod-001", "module_001"),
            ("cvmod-002", "module_002"),
            ("cvmod-003", "module_003"),
            ("cvmod-004", "module_004"),
            ("cvmod-005", "module_005"),
        ]:
            try:
                connection.execute(
                    "UPDATE tools SET tool_id=? WHERE tool_id=?", (new_id, old_id)
                )
            except Exception:
                pass
        # migration：animal-tagger → module_006
        try:
            connection.execute(
                "UPDATE tools SET tool_id='module_006', script_relative_path='cv_framework_runner.py',"
                " name='006 - 動物影像標記' WHERE tool_id='animal-tagger'"
            )
        except Exception:
            pass
        # migration：retire legacy non-module tools
        try:
            connection.execute(
                "UPDATE tools SET enabled=0 WHERE tool_id IN (?, ?)",
                ("opencv-tool", "cv-framework"),
            )
        except Exception:
            pass
        # migration：fix sheet_id "edge_analysis" → "edge-analysis" to match tool_id "sheet-edge-analysis"
        # (CIM_SHEET_ID is now derived by stripping "sheet-" without replacing hyphens)
        try:
            connection.execute(
                "UPDATE sheet_tabs SET sheet_id='edge-analysis' WHERE sheet_id='edge_analysis'"
            )
            connection.execute(
                "UPDATE sheets SET sheet_id='edge-analysis' WHERE sheet_id='edge_analysis'"
            )
        except Exception:
            pass
        # migration：re-enable module_001 (was archived but has proper scripts)
        try:
            connection.execute(
                "UPDATE tools SET enabled=1, name='001 - OpenCV 影像處理' WHERE tool_id='module_001'"
            )
        except Exception:
            pass
        # migration：rename module_008 from old "Annotation Common Component Demo" to new video tracking
        try:
            connection.execute(
                "UPDATE tools SET name='008 - 影片追蹤標注', version='0.1.0',"
                " script_relative_path='cv_framework_runner.py'"
                " WHERE tool_id='module_008'"
            )
        except Exception:
            pass

    def _seed_static_tools(self, connection) -> None:
        """Seed tools that have no plugin.yaml (sheet runners / management /
        external), then apply product-state fixups. Idempotent.

        The data lives in config/seed.yaml (declarative authority) — editing
        that file is enough to add/adjust a no-plugin.yaml tool; no engine.py
        change and the change is reviewable as a git diff.
        """
        seed = _load_static_seed()

        # ── Static seeds: sheet tools + management + external (no plugin.yaml) ─
        rows = [
            (t["tool_id"], t["name"], t.get("script", "sheet_runner.py"),
             str(t.get("version", "1.0.0")), None, "seed", "system", None, 1)
            for t in seed.get("static_tools", [])
        ]
        if rows:
            connection.executemany(
                """
                INSERT OR IGNORE INTO tools (
                    tool_id, name, script_relative_path, version,
                    signature, source_commit, author, approved_at, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        # Disable legacy tools no longer in the product
        disable_ids = seed.get("disable_tools", [])
        if disable_ids:
            connection.execute(
                "UPDATE tools SET enabled = 0 WHERE tool_id IN (%s)"
                % ",".join("?" for _ in disable_ids),
                disable_ids,
            )
        # NOTE: orphaned "sheet-*" tools (no wired tabs -- e.g. the old garbage
        # seed "共用標註功能 - 套件") are NOT blacklisted here by id. They are
        # caught generically by the orphan auto-converge at the end of
        # _reconcile_sheets_from_yaml, which disables ANY enabled sheet tool with
        # no tabs. That replaces per-id whack-a-mole and self-heals existing DBs.
        # Ensure all static-seed active tools are prod-enabled
        prod_ids = seed.get("prod_enable_tools", [])
        if prod_ids:
            connection.execute(
                "UPDATE tools SET enabled_prod = 1 WHERE tool_id IN (%s)"
                % ",".join("?" for _ in prod_ids),
                prod_ids,
            )
        # Rename display name for existing installs (only if old name matches)
        for r in seed.get("renames", []):
            connection.execute(
                "UPDATE tools SET name=? WHERE tool_id=? AND name=?",
                (r["new_name"], r["tool_id"], r["old_name"]),
            )
        # one-time sheet-tab cleanup migrations (e.g. remove iWISC modules from
        # the local annotation sheet)
        for d in seed.get("sheet_tab_deletions", []):
            pids = d.get("plugin_ids", [])
            if not pids:
                continue
            connection.execute(
                "DELETE FROM sheet_tabs WHERE sheet_id=? AND plugin_id IN (%s)"
                % ",".join("?" for _ in pids),
                [d["sheet_id"], *pids],
            )

    def _reconcile_sheets_from_yaml(self, connection) -> list[dict]:
        """Read sheets/*.yaml and reconcile sheet rows + tabs for each definition.

        Adding a new workflow sheet no longer requires touching engine.py —
        just drop a YAML file in sidecar/python-engine/sheets/.

        Returns a list of {sheet_id, missing} for sheets whose tabs couldn't be
        wired because a referenced module isn't registered — surfaced to the
        portal so the author sees *why* their sheet didn't fully appear.
        """
        missing_report: list[dict] = []
        try:
            import yaml
        except ImportError:
            logging.warning("PyYAML not available; skipping sheet YAML reconciliation")
            return missing_report

        # Scan both the platform sheets/ dir and each plugin's sheets/ dir
        # (e.g. plugins/labeling/sheets/). Adding a sheet = drop a YAML in either.
        yaml_paths = sorted((ROOT_DIR / "sheets").glob("*.yaml"))
        yaml_paths += sorted((ROOT_DIR / "plugins").glob("*/sheets/*.yaml"))
        if not yaml_paths:
            return missing_report

        for yaml_path in yaml_paths:
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                logging.warning("Failed to parse %s: %s", yaml_path, exc)
                continue

            sheet_id = data.get("sheet_id")
            if not sheet_id:
                continue

            desired_tabs = [
                (int(t["order"]), t["module_id"], t["label"])
                for t in data.get("tabs", [])
            ]
            if not desired_tabs:
                continue

            name         = data.get("name", sheet_id)
            description  = data.get("description", "")
            enabled_dev  = 1 if data.get("enabled_dev", True)  else 0
            enabled_prod = 1 if data.get("enabled_prod", False) else 0

            # Auto-register the sheet as a launchable tool (tool_id = sheet-<id>),
            # so an engineer who authors a new sheet YAML sees it appear WITHOUT
            # editing engine.py's seed block. Idempotent (INSERT OR IGNORE).
            connection.execute(
                """
                INSERT OR IGNORE INTO tools (
                    tool_id, name, script_relative_path, version,
                    source_commit, author, enabled
                ) VALUES (?, ?, 'sheet_runner.py', '1.0.0', 'sheet.yaml', 'system', 1)
                """,
                (f"sheet-{sheet_id}", name),
            )

            # Skip tab wiring if any required module is missing from the DB.
            # Record WHY in the log so the author isn't left guessing why their
            # sheet didn't appear (R1 gap: silent skip).
            plugin_ids = [mid for _, mid, _ in desired_tabs]
            placeholders = ",".join("?" for _ in plugin_ids)
            existing = {
                row["tool_id"]
                for row in connection.execute(
                    f"SELECT tool_id FROM tools WHERE tool_id IN ({placeholders})",
                    plugin_ids,
                )
            }
            missing = [mid for mid in plugin_ids if mid not in existing]
            if missing:
                logging.warning(
                    "Sheet '%s' tabs not wired: module(s) %s not registered "
                    "(add their plugin.yaml or check the id).",
                    sheet_id, ", ".join(missing),
                )
                missing_report.append({"sheet_id": sheet_id, "missing": missing})
                continue

            current = [
                (row["tab_order"], row["plugin_id"], row["label"])
                for row in connection.execute(
                    "SELECT tab_order, plugin_id, label FROM sheet_tabs"
                    " WHERE sheet_id=? ORDER BY tab_order",
                    (sheet_id,),
                )
            ]
            if current == desired_tabs:
                continue

            connection.execute(
                """
                INSERT OR IGNORE INTO sheets
                    (sheet_id, name, description, enabled_dev, enabled_prod)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sheet_id, name, description, enabled_dev, enabled_prod),
            )
            connection.execute(
                "DELETE FROM sheet_tabs WHERE sheet_id=?", (sheet_id,)
            )
            connection.executemany(
                "INSERT INTO sheet_tabs (sheet_id, tab_order, plugin_id, label)"
                " VALUES (?, ?, ?, ?)",
                [(sheet_id, order, mid, label) for order, mid, label in desired_tabs],
            )

        # ── Orphan auto-convergence (general invariant; SQLite-centric) ──────────
        # An enabled "sheet-*" tool with NO wired tabs can never launch: it would
        # spawn sheet_runner.py without a CIM_PLUGIN_ID and fail with the cryptic
        # "Missing CIM_SHEET_ID or CIM_PLUGIN_ID". Instead of blacklisting such ids
        # one-by-one (whack-a-mole, hard-coded), enforce the invariant generally:
        # disable ANY enabled sheet tool that has no tabs, so it can NEVER reach the
        # portal dropdown. This runs on every _initialize AND every /reload (both
        # call this), so existing DBs self-heal on restart/reload. Each disable is
        # logged with the greppable [CIM-PREFLIGHT] marker for engine.log diagnosis.
        self.orphan_sheets_disabled = []
        for row in connection.execute(
            "SELECT tool_id FROM tools WHERE tool_id LIKE 'sheet-%' AND enabled = 1"
        ).fetchall():
            tool_id = row["tool_id"]
            sid = tool_id[len("sheet-"):]
            has_tab = connection.execute(
                "SELECT 1 FROM sheet_tabs WHERE sheet_id = ? LIMIT 1", (sid,)
            ).fetchone()
            if not has_tab:
                connection.execute(
                    "UPDATE tools SET enabled = 0 WHERE tool_id = ?", (tool_id,)
                )
                self.orphan_sheets_disabled.append(tool_id)
                logging.error(
                    "[CIM-PREFLIGHT] auto-disabled orphan sheet tool %r: no wired "
                    "tabs (missing sheet definition or its modules aren't "
                    "registered). Hidden from the catalog so it cannot fail with "
                    "'Missing CIM_SHEET_ID or CIM_PLUGIN_ID'.", tool_id,
                )
        return missing_report

    def _scan_and_register_plugins(self, connection) -> None:
        """Scan scripts/*/plugin.yaml and upsert each plugin into the DB.

        plugin.yaml is the single source of truth for id, name, vendor, domain,
        enabled state, and runner mapping. New modules just need a plugin.yaml —
        no hardcoded seed required.
        """
        try:
            import yaml
        except ImportError:
            logging.warning("PyYAML not available; skipping plugin.yaml scan")
            return

        _runner_map = {
            "cv_framework":     "cv_framework_runner.py",
            "annotation_runner": "annotation_runner.py",
            "sheet":            "sheet_runner.py",
            "management":       "management_runner.py",
        }
        # Scan scripts/*/plugin.yaml AND each plugin's modules
        # (plugins/<plugin>/modules/<module>/plugin.yaml).
        yaml_paths = sorted((ROOT_DIR / "scripts").glob("*/plugin.yaml"))
        yaml_paths += sorted((ROOT_DIR / "plugins").glob("*/modules/*/plugin.yaml"))
        for yaml_path in yaml_paths:
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                logging.warning("Failed to parse %s: %s", yaml_path, exc)
                continue

            tool_id = data.get("id")
            if not tool_id:
                continue

            runner  = data.get("runner", "cv_framework")
            script  = _runner_map.get(runner, f"{runner}_runner.py")
            name    = data.get("name", tool_id)
            version = str(data.get("version", "1.0.0"))
            enabled = 1 if data.get("enabled", True) else 0
            vendor  = data.get("vendor", "cimcore")
            domain  = data.get("domain") or ""
            deprecated_at = data.get("deprecated_at")
            author  = data.get("author", "system")

            slug = data.get("slug") or None

            connection.execute(
                """
                INSERT OR IGNORE INTO tools (
                    tool_id, name, script_relative_path, version,
                    source_commit, author, enabled, vendor, domain, deprecated_at, slug
                ) VALUES (?, ?, ?, ?, 'plugin.yaml', ?, ?, ?, ?, ?, ?)
                """,
                (tool_id, name, script, version, author, enabled, vendor, domain, deprecated_at, slug),
            )
            # Sync mutable dev/catalog fields from yaml on every startup.
            # Prod visibility is controlled only by publish/management workflows.
            connection.execute(
                """
                UPDATE tools
                SET name=?, script_relative_path=?, version=?, enabled=?,
                    vendor=?, domain=?, deprecated_at=?, slug=?
                WHERE tool_id=?
                """,
                (name, script, version, enabled, vendor, domain, deprecated_at, slug, tool_id),
            )

    def rescan(self) -> dict:
        """Re-scan plugin.yaml + sheet YAML into the DB without restarting.

        Powers DEV hot-reload: an engineer drops/edits a plugin.yaml or sheet
        YAML and hits reload instead of restarting the whole Electron app. Both
        scans are idempotent (INSERT OR IGNORE + UPDATE), so this is safe to call
        repeatedly. Returns the tool_ids newly added since the previous state."""
        with self._connect() as connection:
            before = {row["tool_id"] for row in connection.execute("SELECT tool_id FROM tools")}
            self._scan_and_register_plugins(connection)
            missing_report = self._reconcile_sheets_from_yaml(connection) or []
            after = {row["tool_id"] for row in connection.execute("SELECT tool_id FROM tools")}
        added = sorted(after - before)
        missing_modules = sorted({m for r in missing_report for m in r["missing"]})
        return {"added": added, "total": len(after),
                "missing_sheets": missing_report, "missing_modules": missing_modules}

    def list_tools(self) -> list[ToolDefinition]:
        rows = self._store.list_enabled_tool_definition_rows()
        return [self._row_to_tool(row) for row in rows]

    def set_prod_enabled(self, tool_id: str, enabled: bool) -> None:
        self._store.set_tool_prod_enabled(tool_id, enabled)

    def list_tools_with_prod(self) -> list[tuple]:
        return self._store.list_tools_with_prod_flags()

    def get_tool(self, tool_id: str) -> ToolDefinition:
        row = self._store.get_enabled_tool_definition_row(tool_id)
        if row is None:
            raise KeyError(tool_id)
        return self._row_to_tool(row)

    def _row_to_tool(self, row) -> ToolDefinition:
        return ToolDefinition(
            tool_id=row["tool_id"],
            name=row["name"],
            script_path=TOOLS_DIR / row["script_relative_path"],
            version=row["version"],
            signature=row["signature"],
            source_commit=row["source_commit"],
            author=row["author"],
            approved_at=row["approved_at"],
            slug=row.get("slug"),
        )


def _derive_category(tool_id: str) -> str:
    if tool_id == "labelme-dino":
        return "external"
    if tool_id.startswith("sheet-"):
        return "sheet"
    # 'app-…' = a self-contained external Streamlit app embedded as a top-level
    # tool (one runner, one iframe) — e.g. AI4BI vendored as a submodule.
    if tool_id.startswith("app-"):
        return "app"
    if tool_id.startswith("management-"):
        return "management"
    return "module"


class ToolRegistry:
    def __init__(self, adapter: ToolAdapter) -> None:
        self._adapter = adapter

    def list_tools(self) -> list[ToolInfo]:
        return [
            ToolInfo(
                tool_id=tool.tool_id,
                name=tool.name,
                version=tool.version,
                category=_derive_category(tool.tool_id),
                slug=tool.slug,
            )
            for tool in self._adapter.list_tools()
        ]

    def rescan(self) -> dict:
        return self._adapter.rescan()

    def get(self, tool_id: str) -> ToolDefinition:
        return self._adapter.get_tool(tool_id)

    def set_prod_enabled(self, tool_id: str, enabled: bool) -> None:
        self._adapter.set_prod_enabled(tool_id, enabled)

    def list_tools_with_prod(self) -> list[tuple]:
        return self._adapter.list_tools_with_prod()


def _split_scripts(tool: ToolDefinition) -> tuple[Path, Path]:
    """Return (input_script, output_script).

    Looks for {stem}_input.py / {stem}_output.py next to the main script.
    Falls back to the single script for both sides when split files don't exist.
    """
    parent = tool.script_path.parent
    stem = tool.script_path.stem
    input_script = parent / f"{stem}_input.py"
    output_script = parent / f"{stem}_output.py"
    if input_script.exists() and output_script.exists():
        return input_script, output_script
    return tool.script_path, tool.script_path


def _terminate_process(process: subprocess.Popen, label: str) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            process.wait(timeout=5)
            return
        except Exception:
            logging.warning("Process tree kill failed for %s; falling back to terminate", label)
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logging.warning("Process %s did not exit gracefully; killing", label)
        process.kill()
        process.wait(timeout=5)


def _read_tool_requires(module_id: str) -> list[str]:
    """Read a module's declared Python dependencies from its plugin.yaml `requires:`.

    Powers per-tool dependencies (#7). Returns [] for anything without a module
    folder / plugin.yaml (sheets, management, external tools) — those incur zero
    cost. Never raises: a malformed yaml just yields no extra deps.
    See docs/platform/per-tool-dependencies.md.
    """
    try:
        import yaml  # noqa: PLC0415
        from plugin_loader import find_module_folder  # noqa: PLC0415

        yaml_path = find_module_folder(module_id) / "plugin.yaml"
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        reqs = data.get("requires") or []
        return [str(r) for r in reqs if r and str(r).strip()]
    except Exception:
        return []


# Streamlit readiness budget for a tool launch. A frozen engine.exe re-launches
# itself to host each Streamlit subprocess, whose first boot is slow; when the
# tool also declares `requires:`, the (one-time) pip install + disk churn pushes
# the first launch past the default → the start 500s. Give requires: tools a
# longer first-launch budget (after pre-warming the venv off this budget).
_TOOL_READY_TIMEOUT_DEFAULT = 30.0
_TOOL_READY_TIMEOUT_WITH_DEPS = 120.0


class ToolProcessManager:
    def __init__(self, log_dir: Path, selected_paths_file: Path, db_path: Path) -> None:
        self._log_dir = log_dir.resolve()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._selected_paths_file = selected_paths_file.resolve()
        self._db_path = db_path.resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        SQLiteManagementSchema(self._db_path).ensure_current()
        self._input_process: Optional[subprocess.Popen] = None
        self._output_process: Optional[subprocess.Popen] = None
        self._external_process: Optional[subprocess.Popen] = None
        self._external_log_file = None
        self._external_log_path: Optional[Path] = None
        self._external_ready_file: Optional[Path] = None
        self._external_run_id: Optional[str] = None
        self._external_started_at: Optional[float] = None
        self._external_last_probe: Optional[dict] = None
        self._lock = threading.RLock()
        self._sheet_processes: dict[str, tuple[subprocess.Popen, subprocess.Popen]] = {}
        self._sheet_tab_info: list[dict] = []
        self._sheet_tool_def: Optional[ToolDefinition] = None
        self._sheet_input_script: Optional[Path] = None
        self._sheet_output_script: Optional[Path] = None
        self._tool_id: Optional[str] = None
        self._run_id: Optional[str] = None
        self._input_port: int = 0
        self._output_port: int = 0
        self._preview_process: Optional[subprocess.Popen] = None
        self._preview_tool_id: Optional[str] = None
        self._preview_port: int = 0

    def _make_env(self, tool: ToolDefinition, plugin_id: str = "") -> dict[str, str]:
        env = os.environ.copy()
        env["CIM_TOOL_ID"] = tool.tool_id
        env["CIM_LOG_DIR"] = str(self._log_dir)
        env["CIM_SELECTED_PATHS_FILE"] = str(self._selected_paths_file)
        # tool_id like "module_003" → inject CIM_MODULE_ID=003
        if tool.tool_id.startswith("module_"):
            env["CIM_MODULE_ID"] = tool.tool_id.split("_", 1)[1]
        # tool_id like "sheet-edge-analysis" → inject CIM_SHEET_ID=edge-analysis
        # Strip only the "sheet-" prefix; do NOT replace hyphens, as the sheet_id
        # in the DB may contain hyphens that are part of the original name.
        if tool.tool_id.startswith("sheet-"):
            env["CIM_SHEET_ID"] = tool.tool_id[len("sheet-"):]
        if plugin_id:
            env["CIM_PLUGIN_ID"] = plugin_id
        env["CIM_TOOLS_DB"] = str(self._db_path)

        # Per-tool dependencies (#7): if the module declares `requires:` in its
        # plugin.yaml, ensure an isolated per-tool venv has them and prepend its
        # site-packages onto the subprocess PYTHONPATH (so a tool's own pinned
        # versions win). Modules with no requires return instantly (no venv).
        # Dependency handling never blocks launch — on failure we log and start
        # the subprocess without the extra path. For a sheet tab, plugin_id is
        # the real module being spawned, so key deps on it (not the sheet id).
        deps_module = plugin_id or tool.tool_id
        try:
            requires = _read_tool_requires(deps_module)
            if requires:
                from core.tool_deps import ensure_tool_deps  # noqa: PLC0415

                dep = ensure_tool_deps(deps_module, requires)
                if dep.ok and dep.site_packages:
                    existing = env.get("PYTHONPATH", "")
                    extra = os.pathsep.join(dep.site_packages)
                    env["PYTHONPATH"] = extra + (os.pathsep + existing if existing else "")
                    logging.info("Per-tool deps ready for %s: %s",
                                 deps_module, dep.installed or "(cached)")
                elif not dep.ok:
                    logging.warning("Per-tool deps for %s unavailable: %s",
                                    deps_module, dep.message)
        except Exception as exc:  # never block tool launch on dep handling
            logging.warning("Per-tool dependency handling skipped for %s: %s",
                            deps_module, exc)
        return env

    def _prewarm_deps_and_timeout(self, deps_module: str) -> float:
        """Build the per-tool venv up-front (idempotent) and pick the readiness
        timeout for the upcoming Streamlit launch.

        Resolving deps here — before any process is spawned and before the
        wait_for_port clock starts — keeps a slow first-run `pip install` off the
        readiness budget, and returns a longer budget so the first launch of a
        `requires:` tool doesn't 500 while the frozen Streamlit subprocess boots.
        No requires → instant, default budget. Never raises (logged)."""
        try:
            requires = _read_tool_requires(deps_module)
        except Exception:
            requires = []
        if not requires:
            return _TOOL_READY_TIMEOUT_DEFAULT
        try:
            from core.tool_deps import ensure_tool_deps  # noqa: PLC0415
            logging.info("Resolving per-tool dependencies for %s before launch "
                         "(first run may install %s)…", deps_module, requires)
            ensure_tool_deps(deps_module, requires)
        except Exception as exc:  # never block launch on dep handling
            logging.warning("Per-tool dep prewarm skipped for %s: %s", deps_module, exc)
        return _TOOL_READY_TIMEOUT_WITH_DEPS

    def _spawn(self, script: Path, tool: ToolDefinition, port: int, label: str,
               plugin_id: str = "") -> subprocess.Popen:
        tag = f"{plugin_id}-{label}" if plugin_id else label
        log_file = (self._log_dir / f"streamlit-{tool.tool_id}-{tag}.log").open("a", encoding="utf-8")
        command = streamlit_command_for_script(script, port, self._log_dir)
        logging.info("Starting Streamlit %s for %s on port %s", tag, tool.tool_id, port)
        env = self._make_env(tool, plugin_id)
        env["CIM_TOOL_LAYER"] = label
        return subprocess.Popen(
            command,
            cwd=str(ROOT_DIR),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _get_sheet_tabs(self, sheet_id: str) -> list[dict]:
        db_path = self._db_path
        def _query_tabs() -> list[dict]:
            rows = SQLiteManagementStore(db_path).list_sheet_tab_rows(sheet_id)
            return [{"plugin_id": r["plugin_id"], "label": r["label"]} for r in rows]

        try:
            tabs = _query_tabs()
            if tabs:
                return tabs
        except Exception as exc:
            logging.info("Sheet tabs not ready for %s; syncing sheets: %s", sheet_id, exc)

        try:
            from plugin_registry import PluginRegistry

            PluginRegistry(db_path=db_path, scripts_dir=ROOT_DIR / "scripts").sync_sheets()
            return _query_tabs()
        except Exception as exc:
            logging.warning("Unable to load sheet tabs for %s: %s", sheet_id, exc)
            return []

    def start(self, tool: ToolDefinition) -> ToolStartResponse:
        with self._lock:
            self.stop()
            if _derive_category(tool.tool_id) == "external":
                return self._start_external(tool)
            if _derive_category(tool.tool_id) == "sheet":
                return self._start_sheet(tool)
            if _derive_category(tool.tool_id) == "app":
                return self._start_app(tool)
            return self._start_regular(tool)

    def _labelme_dino_exe(self) -> Path:
        env_path = os.environ.get("LABELME_DINO_EXE", "").strip()
        candidates = []
        if env_path:
            candidates.append(Path(env_path))
        project_root = ROOT_DIR.parents[1] if len(ROOT_DIR.parents) > 1 else ROOT_DIR
        candidates.extend([
            project_root / "external_exe" / "LabelMe_Dino_launcher" / "LabelMe_Dino.exe",
            project_root / "LabelMe_Dino" / "dist" / "LabelMe_Dino_launcher" / "LabelMe_Dino.exe",
            ROOT_DIR.parent / "labelme-dino" / "LabelMe_Dino.exe",
            ROOT_DIR / "labelme-dino" / "LabelMe_Dino.exe",
        ])
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError(candidates[0] if candidates else "LabelMe_Dino.exe")

    def _labelme_dino_project_root(self) -> Path:
        return ROOT_DIR.parents[1] if len(ROOT_DIR.parents) > 1 else ROOT_DIR

    def _labelme_dino_app_root(self) -> Path:
        project_root = self._labelme_dino_project_root()
        candidates = [
            project_root / "LabelMe_Dino",
            ROOT_DIR.parent / "labelme-dino",
            ROOT_DIR / "labelme-dino",
        ]
        try:
            exe = self._labelme_dino_exe()
            candidates.insert(0, exe.parent)
            candidates.insert(1, exe.parent / "app")
        except FileNotFoundError:
            pass
        for candidate in candidates:
            if (candidate / "main.py").exists() and (candidate / "src").exists():
                return candidate
        return candidates[0]

    def _labelme_dino_runtime_python(self) -> Optional[Path]:
        env = self._labelme_dino_env()
        runtime = env.get("LABELME_DINO_RUNTIME", "").strip()
        if runtime:
            python = Path(runtime) / "Scripts" / "python.exe"
            if python.exists():
                return python
        return None

    def _labelme_dino_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        project_root = self._labelme_dino_project_root()
        env["CIM_REPO_ROOT"] = str(project_root)
        if not env.get("LABELME_DINO_RUNTIME"):
            runtime = project_root / "LabelMe_Dino" / ".venv"
            if runtime.exists():
                env["LABELME_DINO_RUNTIME"] = str(runtime)
        runtime_path = env.get("LABELME_DINO_RUNTIME", "").strip()
        if runtime_path:
            site_packages = Path(runtime_path) / "Lib" / "site-packages"
            path_parts = [
                Path(runtime_path) / "Scripts",
                site_packages / "torch" / "lib",
                site_packages / "PyQt5" / "Qt5" / "bin",
                site_packages / "cv2",
            ]
            existing_path = env.get("PATH", "")
            env["PATH"] = os.pathsep.join([str(p) for p in path_parts if p.exists()] + [existing_path])
            qt_plugins = site_packages / "PyQt5" / "Qt5" / "plugins"
            if qt_plugins.exists():
                env["QT_PLUGIN_PATH"] = str(qt_plugins)
                env["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(qt_plugins / "platforms")
        if not env.get("LABELME_EXE"):
            labelme_exe = project_root / "LabelMe_Dino" / ".venv" / "Scripts" / "labelme.exe"
            if labelme_exe.exists():
                env["LABELME_EXE"] = str(labelme_exe)
        if not env.get("XANYLABELING_EXE"):
            xany_exe = project_root / ".venv-xanylabeling" / "Scripts" / "xanylabeling.exe"
            if xany_exe.exists():
                env["XANYLABELING_EXE"] = str(xany_exe)
        return env

    def _runtime_paths(self) -> dict[str, str]:
        env = self._labelme_dino_env()
        values: dict[str, str] = {}
        for key in ("CIM_REPO_ROOT", "LABELME_DINO_RUNTIME", "LABELME_EXE", "XANYLABELING_EXE"):
            if env.get(key):
                values[key.lower()] = env[key]
        try:
            values["labelme_dino_exe"] = str(self._labelme_dino_exe())
        except FileNotFoundError as exc:
            values["labelme_dino_exe"] = str(exc)
        return values

    def _labelme_dino_probe(self, timeout: float = 30.0) -> dict:
        try:
            exe = self._labelme_dino_exe()
        except FileNotFoundError as exc:
            result = {
                "ok": False,
                "error": f"video_annotator executable not found: {exc}",
                "paths": self._runtime_paths(),
            }
            self._external_last_probe = result
            return result

        try:
            completed = subprocess.run(
                [str(exe), "--probe-runtime"],
                cwd=str(exe.parent),
                env=self._labelme_dino_env(),
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            fallback = self._labelme_dino_python_probe(timeout=timeout)
            fallback["launcher_error"] = str(exc)
            self._external_last_probe = fallback
            return fallback

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        payload: dict = {}
        for line in reversed(stdout.splitlines()):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        ok = completed.returncode == 0 and bool(payload.get("ok", False))
        result = {
            "ok": ok,
            "exit_code": completed.returncode,
            "probe": payload,
            "launcher": "exe",
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
            "paths": self._runtime_paths(),
        }
        if not ok:
            result["error"] = payload.get("error") or stderr or stdout or "Runtime probe returned an error"
        self._external_last_probe = result
        return result

    def _labelme_dino_python_probe(self, timeout: float = 30.0) -> dict:
        python = self._labelme_dino_runtime_python()
        if python is None:
            return {
                "ok": False,
                "error": "video_annotator runtime python.exe not found",
                "paths": self._runtime_paths(),
            }
        code = (
            "import json, sys; "
            "import torch, cv2, transformers; "
            "from PyQt5.QtCore import QT_VERSION_STR; "
            "print(json.dumps({"
            "'ok': True, "
            "'python': sys.version.split()[0], "
            "'torch': getattr(torch, '__version__', 'unknown'), "
            "'cuda_available': bool(torch.cuda.is_available()), "
            "'cv2': getattr(cv2, '__version__', 'unknown'), "
            "'transformers': getattr(transformers, '__version__', 'unknown'), "
            "'qt': QT_VERSION_STR"
            "}))"
        )
        try:
            completed = subprocess.run(
                [str(python), "-c", code],
                cwd=str(self._labelme_dino_app_root()),
                env=self._labelme_dino_env(),
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Runtime python probe failed: {exc}",
                "paths": self._runtime_paths(),
            }

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        payload: dict = {}
        for line in reversed(stdout.splitlines()):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        ok = completed.returncode == 0 and bool(payload.get("ok", False))
        return {
            "ok": ok,
            "exit_code": completed.returncode,
            "probe": payload,
            "launcher": "python",
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
            "paths": self._runtime_paths(),
            **({} if ok else {"error": payload.get("error") or stderr or stdout or "Runtime python probe returned an error"}),
        }

    def _labelme_dino_command(self, ready_file: Path, probe: dict) -> tuple[list[str], Path]:
        if probe.get("launcher") == "exe":
            exe = self._labelme_dino_exe()
            return [str(exe), "--ready-file", str(ready_file)], exe.parent

        python = self._labelme_dino_runtime_python()
        if python is None:
            raise RuntimeError("video_annotator runtime python.exe not found")
        app_root = self._labelme_dino_app_root()
        return [str(python), str(app_root / "main.py"), "--ready-file", str(ready_file)], app_root

    def _wait_for_ready_file(self, ready_file: Path, timeout: float = 45.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._external_process and self._external_process.poll() is not None:
                return {
                    "ok": False,
                    "error": f"External process exited with code {self._external_process.returncode}",
                }
            try:
                if ready_file.exists():
                    return json.loads(ready_file.read_text(encoding="utf-8"))
            except Exception as exc:
                return {"ok": False, "error": f"Ready file could not be read: {exc}"}
            time.sleep(0.25)
        return {"ok": False, "error": f"Ready file was not created within {timeout:.0f}s"}

    def runtime_status(self) -> dict:
        return {
            "ok": True,
            "platform": platform.platform(),
            "python": sys.version,
            "root_dir": str(ROOT_DIR),
            "log_dir": str(self._log_dir),
            "paths": self._runtime_paths(),
            "labelme_dino": self._external_last_probe or self._labelme_dino_probe(timeout=30.0),
        }

    def diagnostics(self) -> dict:
        status = {"active": False}
        if self._tool_id:
            if self._external_process is not None:
                ready = bool(self._external_ready_file and self._external_ready_file.exists())
                status = {
                    "active": True,
                    "tool_id": self._tool_id,
                    "category": "external",
                    "alive": self._external_process.poll() is None,
                    "pid": self._external_process.pid,
                    "ready": ready,
                    "run_id": self._external_run_id,
                    "started_at": self._external_started_at,
                    "log_path": str(self._external_log_path) if self._external_log_path else None,
                    "ready_file": str(self._external_ready_file) if self._external_ready_file else None,
                }
            else:
                status = {"active": True, "tool_id": self._tool_id,
                          "category": _derive_category(self._tool_id), "run_id": self._run_id}
        return {
            "ok": True,
            "sidecar_pid": os.getpid(),
            "root_dir": str(ROOT_DIR),
            "log_dir": str(self._log_dir),
            "active_tool": status,
            "runtime": self.runtime_status(),
            # Non-empty => git submodules not checked out; portal can show a banner.
            "missing_submodules": check_submodules(),
            # Running engine identity — confirm a fix is actually live (not a
            # stale sidecar). boot_id changes on every restart.
            "commit": engine_commit(),
            "boot_id": _BOOT_ID,
        }

    def _start_external(self, tool: ToolDefinition) -> ToolStartResponse:
        probe = self._labelme_dino_probe()
        if not probe.get("ok"):
            raise RuntimeError(f"video_annotator runtime probe failed: {probe.get('error', 'unknown error')}")

        run_id = uuid.uuid4().hex[:12]
        log_path = self._log_dir / f"{tool.tool_id}-{run_id}.log"
        ready_file = self._log_dir / f"{tool.tool_id}-{run_id}.ready.json"
        ready_file.unlink(missing_ok=True)
        command, cwd = self._labelme_dino_command(ready_file, probe)
        self._external_log_file = log_path.open("a", encoding="utf-8")
        logging.info("Starting external tool %s: %s", tool.tool_id, " ".join(command))
        self._external_process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=self._labelme_dino_env(),
            stdout=self._external_log_file,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._tool_id = tool.tool_id
        self._external_log_path = log_path
        self._external_ready_file = ready_file
        self._external_run_id = run_id
        self._run_id = run_id
        self._external_started_at = time.time()
        ready_payload = self._wait_for_ready_file(ready_file)
        if not ready_payload.get("ok", False):
            self.stop()
            raise RuntimeError(f"video_annotator did not become ready: {ready_payload.get('error', 'unknown error')}")
        SQLiteManagementStore(self._db_path).start_tool_run(
            tool.tool_id,
            "external",
            "external-window",
            actor=os.environ.get("USERNAME") or os.environ.get("USER") or "system",
            pid=self._external_process.pid,
            log_path=str(log_path),
            run_id=run_id,
        )
        return ToolStartResponse(
            tool_id=tool.tool_id,
            input_url="",
            output_url="",
            input_port=0,
            output_port=0,
            category="external",
            mode="external-window",
            pid=self._external_process.pid,
            run_id=run_id,
            ready=True,
            log_path=str(log_path),
            message="video_annotator external window is ready",
            runtime=probe.get("probe") if isinstance(probe, dict) else None,
        )

    def _start_regular(self, tool: ToolDefinition) -> ToolStartResponse:
        result_file = self._log_dir / f"{tool.tool_id}_result.json"
        result_file.unlink(missing_ok=True)

        input_script, output_script = _split_scripts(tool)
        if not input_script.exists():
            raise FileNotFoundError(input_script)
        if not output_script.exists():
            raise FileNotFoundError(output_script)

        # Pre-warm per-tool deps off the readiness budget; longer budget if any.
        ready_timeout = self._prewarm_deps_and_timeout(tool.tool_id)

        input_port = find_free_port()
        output_port = find_free_port(exclude={input_port})

        self._input_process = self._spawn(input_script, tool, input_port, "input")
        self._output_process = self._spawn(output_script, tool, output_port, "output")
        self._tool_id = tool.tool_id

        if not wait_for_port(input_port, timeout=ready_timeout):
            self.stop()
            raise RuntimeError(f"Streamlit input for {tool.tool_id} did not become ready in time")
        if not wait_for_port(output_port, timeout=ready_timeout):
            self.stop()
            raise RuntimeError(f"Streamlit output for {tool.tool_id} did not become ready in time")

        run_id = SQLiteManagementStore(self._db_path).start_tool_run(
            tool.tool_id,
            _derive_category(tool.tool_id),
            "iframe",
            actor=os.environ.get("USERNAME") or os.environ.get("USER") or "system",
            input_port=input_port,
            output_port=output_port,
            pid=self._input_process.pid if self._input_process else None,
        )
        self._run_id = run_id
        self._input_port = input_port
        self._output_port = output_port
        return ToolStartResponse(
            tool_id=tool.tool_id,
            input_url=f"http://127.0.0.1:{input_port}",
            output_url=f"http://127.0.0.1:{output_port}",
            input_port=input_port,
            output_port=output_port,
            category=_derive_category(tool.tool_id),
            run_id=run_id,
        )

    def _start_app(self, tool: ToolDefinition) -> ToolStartResponse:
        """Launch a self-contained external Streamlit app in ONE iframe.

        Unlike _start_regular (cv_framework input+output panes) or _start_sheet
        (multi-tab), an 'app' tool (tool_id 'app-…') is a full external Streamlit
        application — e.g. AI4BI, developed in its own repo and vendored as a
        git submodule under vendor/, installed editable into the engine's Python.
        We spawn its runner once and expose a single URL; the portal renders one
        iframe. The app owns its own page config / layout, so we must NOT wrap it
        in the cv_framework chrome.
        """
        result_file = self._log_dir / f"{tool.tool_id}_result.json"
        result_file.unlink(missing_ok=True)

        script = tool.script_path
        if not script.exists():
            raise FileNotFoundError(script)

        ready_timeout = self._prewarm_deps_and_timeout(tool.tool_id)
        port = find_free_port()
        self._input_process = self._spawn(script, tool, port, "app")
        self._tool_id = tool.tool_id

        if not wait_for_port(port, timeout=ready_timeout):
            self.stop()
            raise RuntimeError(f"Streamlit app for {tool.tool_id} did not become ready in time")

        run_id = SQLiteManagementStore(self._db_path).start_tool_run(
            tool.tool_id,
            _derive_category(tool.tool_id),
            "iframe",
            actor=os.environ.get("USERNAME") or os.environ.get("USER") or "system",
            input_port=port,
            output_port=port,
            pid=self._input_process.pid if self._input_process else None,
        )
        self._run_id = run_id
        self._input_port = port
        self._output_port = port
        url = f"http://127.0.0.1:{port}"
        return ToolStartResponse(
            tool_id=tool.tool_id,
            input_url=url,
            output_url=url,
            input_port=port,
            output_port=port,
            category=_derive_category(tool.tool_id),
            run_id=run_id,
        )

    def _start_one_sheet_tab(self, plugin_id: str) -> dict:
        """Spawn a single sheet tab and wait until both Streamlit ports are ready."""
        with self._lock:
            tab = next((t for t in self._sheet_tab_info if t["plugin_id"] == plugin_id), None)
            if tab is None:
                raise KeyError(f"Unknown sheet tab: {plugin_id}")
            if tab.get("ready"):
                return dict(tab)

            input_port = tab["input_port"]
            output_port = tab["output_port"]

            if plugin_id not in self._sheet_processes:
                if self._sheet_tool_def is None or self._sheet_input_script is None or self._sheet_output_script is None:
                    raise RuntimeError("Sheet tool definition is not available for lazy start")
                input_process = self._spawn(self._sheet_input_script, self._sheet_tool_def, input_port, "input", plugin_id)
                output_process = self._spawn(self._sheet_output_script, self._sheet_tool_def, output_port, "output", plugin_id)
                self._sheet_processes[plugin_id] = (input_process, output_process)

        # Longer readiness budget when this tab's module declares `requires:`
        # (first-run pip install + frozen Streamlit boot). Deps were built during
        # the spawn above (_make_env).
        ready_timeout = (_TOOL_READY_TIMEOUT_WITH_DEPS
                         if _read_tool_requires(plugin_id) else _TOOL_READY_TIMEOUT_DEFAULT)
        if not wait_for_port(input_port, timeout=ready_timeout):
            raise RuntimeError(f"Sheet tab {plugin_id} input did not become ready in time")
        if not wait_for_port(output_port, timeout=ready_timeout):
            raise RuntimeError(f"Sheet tab {plugin_id} output did not become ready in time")

        with self._lock:
            tab["input_url"] = f"http://127.0.0.1:{input_port}"
            tab["output_url"] = f"http://127.0.0.1:{output_port}"
            tab["ready"] = True
            return dict(tab)

    def _prewarm_remaining_tabs(self) -> None:
        for tab in list(self._sheet_tab_info):
            if tab.get("ready"):
                continue
            if self._tool_id is None:
                return
            try:
                self._start_one_sheet_tab(tab["plugin_id"])
            except Exception as exc:
                logging.warning("Pre-warm tab %s failed: %s", tab["plugin_id"], exc)
            time.sleep(0.8)

    def _start_sheet(self, tool: ToolDefinition) -> ToolStartResponse:
        sheet_id = tool.tool_id[len("sheet-"):]
        tabs = self._get_sheet_tabs(sheet_id)
        if not tabs:
            # Orphaned sheet: a "sheet-*" tool row with no sheet definition / tabs
            # (its sheets/*.yaml is missing or its modules aren't registered).
            # Previously this silently fell back to _start_regular, which launched
            # sheet_runner.py WITHOUT a plugin_id -> the cryptic, hard-to-diagnose
            # "Missing CIM_SHEET_ID or CIM_PLUGIN_ID". Fail loudly instead, with a
            # greppable [CIM-PREFLIGHT] marker and an actionable message (surfaces
            # to the portal as HTTP 500 via the start_tool handler).
            msg = (
                f"Sheet '{sheet_id}' has no tabs -- its definition is missing, so "
                f"tool '{tool.tool_id}' is an orphan. Add "
                f"sidecar/python-engine/sheets/{sheet_id}.yaml (with tabs whose "
                f"module_id are registered), or remove the tool. "
                f"(孤兒 sheet：缺對應的 sheet YAML 定義或模組未註冊)"
            )
            logging.error("[CIM-PREFLIGHT] %s", msg)
            raise RuntimeError(msg)

        input_script, output_script = _split_scripts(tool)
        if not input_script.exists():
            raise FileNotFoundError(input_script)
        if not output_script.exists():
            raise FileNotFoundError(output_script)

        used_ports: set[int] = set()
        tab_info: list[dict] = []

        for tab in tabs:
            plugin_id = tab["plugin_id"]
            # Clear stale result files per tab
            (self._log_dir / f"sheet_{sheet_id}_{plugin_id}_result.json").unlink(missing_ok=True)

            in_port = find_free_port(exclude=used_ports)
            used_ports.add(in_port)
            out_port = find_free_port(exclude=used_ports)
            used_ports.add(out_port)

            tab_info.append({
                "plugin_id": plugin_id,
                "label": tab["label"],
                "input_port": in_port,
                "output_port": out_port,
                "input_url": "",
                "output_url": "",
                "ready": False,
            })

        self._sheet_tab_info = tab_info
        self._sheet_tool_def = tool
        self._sheet_input_script = input_script
        self._sheet_output_script = output_script
        self._tool_id = tool.tool_id

        first = self._start_one_sheet_tab(tab_info[0]["plugin_id"])
        if len(tab_info) > 1:
            threading.Thread(target=self._prewarm_remaining_tabs, daemon=True).start()

        run_id = SQLiteManagementStore(self._db_path).start_tool_run(
            tool.tool_id,
            "sheet",
            "iframe",
            actor=os.environ.get("USERNAME") or os.environ.get("USER") or "system",
            input_port=first["input_port"],
            output_port=first["output_port"],
            pid=self._sheet_processes[first["plugin_id"]][0].pid if first["plugin_id"] in self._sheet_processes else None,
        )
        self._run_id = run_id
        return ToolStartResponse(
            tool_id=tool.tool_id,
            input_url=first["input_url"],
            output_url=first["output_url"],
            input_port=first["input_port"],
            output_port=first["output_port"],
            category="sheet",
            sheet_tabs=[SheetTabInfo(**t) for t in tab_info],
            run_id=run_id,
        )

    def stop(self) -> None:
        with self._lock:
            run_id = self._run_id
            if run_id:
                try:
                    SQLiteManagementStore(self._db_path).finish_tool_run(run_id, "stopped")
                except Exception as exc:
                    logging.warning("Unable to finish run %s: %s", run_id, exc)
                self._run_id = None
            if self._external_process:
                if self._external_process.poll() is None:
                    _terminate_process(self._external_process, f"{self._tool_id}-external")
                self._external_process = None
            if self._external_log_file:
                self._external_log_file.close()
                self._external_log_file = None
            self._external_log_path = None
            self._external_ready_file = None
            self._external_run_id = None
            self._external_started_at = None
            if self._input_process:
                _terminate_process(self._input_process, f"{self._tool_id}-input")
                self._input_process = None
            if self._output_process:
                _terminate_process(self._output_process, f"{self._tool_id}-output")
                self._output_process = None
            for plugin_id, (in_p, out_p) in self._sheet_processes.items():
                _terminate_process(in_p, f"{self._tool_id}-sheet-{plugin_id}-input")
                _terminate_process(out_p, f"{self._tool_id}-sheet-{plugin_id}-output")
            self._sheet_processes = {}
            self._sheet_tab_info = []
            self._sheet_tool_def = None
            self._sheet_input_script = None
            self._sheet_output_script = None
            self._tool_id = None
            self._input_port = 0
            self._output_port = 0

    def start_preview(self, tool: ToolDefinition) -> dict:
        """Start the module's input page as a side process without stopping the current tool."""
        self.stop_preview()
        input_script, _ = _split_scripts(tool)
        if not input_script.exists():
            raise FileNotFoundError(input_script)
        port = find_free_port()
        self._preview_process = self._spawn(input_script, tool, port, "preview")
        self._preview_tool_id = tool.tool_id
        self._preview_port = port
        if not wait_for_port(port):
            self.stop_preview()
            raise RuntimeError(f"Preview for {tool.tool_id} did not start in time")
        return {
            "tool_id": tool.tool_id,
            "input_url": f"http://127.0.0.1:{port}",
            "input_port": port,
        }

    def stop_preview(self) -> None:
        if self._preview_process is not None:
            if self._preview_process.poll() is None:
                _terminate_process(self._preview_process, f"{self._preview_tool_id}-preview")
            self._preview_process = None
        self._preview_tool_id = None
        self._preview_port = 0

    def preview_status(self) -> dict:
        if self._preview_process is None:
            return {"active": False}
        alive = self._preview_process.poll() is None
        port = self._preview_port
        return {
            "active": alive,
            "tool_id": self._preview_tool_id,
            "input_url": f"http://127.0.0.1:{port}" if alive and port else "",
            "input_alive": alive,
        }


class SelectedPathStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self.set_paths([])

    def set_paths(self, paths: list[str]) -> None:
        safe_paths = [str(Path(path)) for path in paths]
        self._path.write_text(json.dumps({"paths": safe_paths}, indent=2), encoding="utf-8")

    def get_paths(self) -> list[str]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        paths = data.get("paths", [])
        return paths if isinstance(paths, list) else []


def find_free_port(exclude: set[int] | None = None) -> int:
    for _ in range(10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        if not exclude or port not in exclude:
            return port
    raise RuntimeError("Could not find a free port not in the excluded set")


def wait_for_port(port: int, timeout: float = 30.0, interval: float = 0.3) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(interval)
    return False


def streamlit_command_for_script(script: Path, port: int, log_dir: Path) -> list[str]:
    log_dir_arg = ["--log-dir", str(log_dir)]
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-streamlit-script", str(script), "--tool-port", str(port)] + log_dir_arg

    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--run-streamlit-script",
        str(script),
        "--tool-port",
        str(port),
    ] + log_dir_arg


def run_streamlit_script(script_path: str, port: int) -> None:
    # In the frozen exe, streamlit defaults global.developmentMode=true, which
    # forbids setting server.port ("server.port does not work when
    # global.developmentMode is true") and crashes every tool subprocess. Force
    # the normal production setting so our explicit --server.port is accepted.
    # Harmless in dev (already false). setdefault respects an explicit override.
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    import streamlit.web.cli as streamlit_cli

    sys.argv = [
        "streamlit",
        "run",
        script_path,
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--server.runOnSave",
        "false",
        "--server.fileWatcherType",
        "none",
        "--client.toolbarMode",
        "minimal",
        "--browser.gatherUsageStats",
        "false",
    ]
    streamlit_cli.main()


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "engine.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ── External image bridge ─────────────────────────────────────────────────────

_ext_queue: list[dict] = []
_ext_queue_lock = threading.Lock()


def _ext_download_image(image_url: str, queue_dir: Path) -> Path:
    parsed = urllib.parse.urlparse(image_url)
    raw_name = Path(parsed.path).name or "image.jpg"
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw_name)
    dest = queue_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    queue_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(image_url, headers={"User-Agent": "CIM-Bridge/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    return dest


def _ext_launch_xanylabeling(local_path: Path, log_dir: Path) -> None:
    xany_exe = os.environ.get("XANYLABELING_EXE", "")
    if not xany_exe or not Path(xany_exe).exists():
        raise RuntimeError("xanylabeling 未設定（XANYLABELING_EXE 環境變數未指向有效執行檔）")
    xany_work_dir = log_dir / "xanylabeling_state" / "external"
    xany_work_dir.mkdir(parents=True, exist_ok=True)
    venv_root = Path(xany_exe).parents[1]
    venv_sp = str(venv_root / "Lib" / "site-packages")
    launch_stmt = f"import sys; sys.path.insert(0, r'{venv_sp}'); from anylabeling.app import main; main()"
    python_exe = Path(xany_exe).parent / "python.exe"
    python_cmd = [str(python_exe)] if python_exe.exists() else ["py", "-3.11"]
    cmd = python_cmd + ["-c", launch_stmt,
                        "--filename", str(local_path),
                        "--output", str(local_path.parent),
                        "--work-dir", str(xany_work_dir),
                        "--nodata", "--autosave", "--no-auto-update-check"]
    subprocess.Popen(cmd)


def _ext_launch_labeling_tool(tool: str, local_path: Path, log_dir: Path) -> None:
    normalized = (tool or "x-anylabeling").strip().lower().replace("_", "-")
    if normalized in {"xanylabeling", "x-anylabeling"}:
        _ext_launch_xanylabeling(local_path, log_dir)
        return
    if normalized == "labelme":
        labelme_exe = os.environ.get("LABELME_EXE", "labelme")
        subprocess.Popen([labelme_exe, str(local_path), "--output", str(local_path.with_suffix(".json")), "--nodata", "--autosave"])
        return
    if normalized == "isat":
        isat_exe = os.environ.get("ISAT_EXE", "isat-sam")
        subprocess.Popen([isat_exe], cwd=str(local_path.parent))
        return
    raise RuntimeError(f"Unsupported labeling tool: {tool}")


def create_app(
    manager: ToolProcessManager,
    registry: ToolRegistry,
    selected_paths: SelectedPathStore,
    db_path: Path,
    log_dir: Path = Path("logs"),
) -> FastAPI:
    app = FastAPI(title="CIM Python Sidecar", version="0.1.0")

    # Auto-register any scaffolded non-REST connectors (core/integrations/connectors/*.py
    # exposing register()), so `scaffold connector` → drop file → restart/reload works
    # with no call-site edits. Best-effort: a broken connector never blocks startup.
    try:
        from core.integrations.registry import autodiscover  # noqa: PLC0415
        _registered = autodiscover()
        if _registered:
            logging.info("Auto-registered connectors: %s", ", ".join(_registered))
    except Exception as _exc:  # noqa: BLE001
        logging.warning("connector autodiscover skipped: %s", _exc)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/whoami")
    def whoami() -> dict:
        """Current RBAC role (so the portal can show it and prove RBAC is live)."""
        from auth_provider import AuthProvider, VALID_ROLES  # noqa: PLC0415
        return {"role": AuthProvider(db_path).get_current_role(), "roles": list(VALID_ROLES)}

    @app.post("/set-role")
    def set_role(body: dict = Body(...)) -> dict:
        """DEV role switch: write the identity file so an admin can see RBAC take
        effect (operators/viewers lose tools / execute). In PROD identity comes
        from CIM_IDENTITY_FILE (SSO/IdP), so this is disabled there."""
        if os.environ.get("CIM_DEV_MODE", "1") != "1":
            raise HTTPException(status_code=403, detail="role switch disabled in PROD (use SSO/IdP)")
        from auth_provider import set_identity  # noqa: PLC0415
        try:
            set_identity(str(body.get("role", "")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "ok", "role": str(body.get("role")).strip().lower()}

    @app.get("/version")
    def version() -> dict:
        return {
            "name": "CIM Python Sidecar",
            "version": app.version,
            "commit": engine_commit(),
            "booted_at": _BOOTED_AT,
            "boot_id": _BOOT_ID,
            "db_path": str(db_path),
            "root_dir": str(ROOT_DIR),
            "pid": os.getpid(),
        }

    @app.get("/runtime")
    def runtime() -> dict:
        return manager.runtime_status()

    @app.get("/diagnostics")
    def diagnostics() -> dict:
        return manager.diagnostics()

    @app.post("/reload")
    def reload_catalog() -> dict:
        """Hot-reload: re-scan plugin.yaml + sheet YAML into the catalog AND
        re-run connector autodiscover, without restarting the app. An engineer
        who just scaffolded/edited a tool (or dropped a connector) calls this (or
        the portal's reload button) and the new/changed item appears."""
        try:
            result = registry.rescan()
            # Symmetry with module/sheet hot-reload: a freshly scaffolded
            # connector (core/integrations/connectors/*.py) becomes usable too.
            try:
                from core.integrations.registry import autodiscover  # noqa: PLC0415
                result["connectors"] = autodiscover(force=True)  # re-scan for newly dropped connectors
            except Exception as exc:  # noqa: BLE001
                logging.warning("reload connector autodiscover skipped: %s", exc)
            # Fleet distribution (#1): also re-pull approved artifacts so a device
            # picks up newly-published tools on reload (no restart). No-op unless
            # CIM_DISTRIBUTION_SOURCE is set.
            _dist_source = os.environ.get("CIM_DISTRIBUTION_SOURCE", "").strip()
            if _dist_source:
                result["distribution"] = pull_distribution_into_catalog(db_path, _dist_source)
            return {"status": "ok", **result}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/tools", response_model=list[ToolInfo])
    def tools() -> list[ToolInfo]:
        all_tools = registry.list_tools()
        if os.environ.get("CIM_DEV_MODE", "1") != "1":
            all_tools = [t for t in all_tools if t.category != "management"]
            prod_rows = registry.list_tools_with_prod()
            prod_enabled = {tool_id for tool_id, _, _, ep in prod_rows if ep}
            store = SQLiteManagementStore(db_path)
            visible_tools: list[ToolInfo] = []
            for tool in all_tools:
                if tool.tool_id not in prod_enabled:
                    continue
                if tool.tool_id.startswith("module_"):
                    issues = validate_module_snapshot_content(
                        tool.tool_id,
                        store.get_active_snapshot_content(tool.tool_id),
                    )
                    if issues:
                        continue
                if tool.tool_id.startswith("sheet-"):
                    sheet_id = tool.tool_id[len("sheet-"):]
                    if validate_sheet_prod_readiness(db_path, sheet_id, store=store):
                        continue
                visible_tools.append(tool)
            all_tools = visible_tools
        return all_tools

    @app.patch("/tools/{tool_id}/prod-enabled")
    def set_prod_enabled(tool_id: str, body: ProdEnabledRequest = Body(...)) -> dict:
        try:
            store = SQLiteManagementStore(db_path)
            if body.enabled:
                if tool_id.startswith("module_"):
                    row = store.get_tool_catalog_row(tool_id)
                    if row is None:
                        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_id}")
                    active = store.get_active_snapshot_content(tool_id)
                    snapshot_issues = validate_module_snapshot_content(tool_id, active)
                    if snapshot_issues:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": "Module cannot be shown in Prod yet.",
                                "issues": snapshot_issues,
                            },
                        )
                elif tool_id.startswith("sheet-"):
                    sheet_id = tool_id[len("sheet-"):]
                    issues = validate_sheet_prod_readiness(db_path, sheet_id, store=store)
                    if issues:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": "Sheet cannot be shown in Prod yet.",
                                "issues": [
                                    {
                                        "sheet_id": issue.sheet_id,
                                        "plugin_id": issue.plugin_id,
                                        "label": issue.label,
                                        "issue": issue.issue,
                                    }
                                    for issue in issues
                                ],
                            },
                        )
                    store.set_sheet_enabled(sheet_id, True, mode="prod")
                    return {"tool_id": tool_id, "sheet_id": sheet_id, "enabled_prod": True}
                elif store.get_tool_catalog_row(tool_id) is None:
                    raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_id}")
            if tool_id.startswith("sheet-"):
                sheet_id = tool_id[len("sheet-"):]
                if store.get_sheet_row(sheet_id) is None:
                    raise HTTPException(status_code=404, detail=f"Unknown sheet: {sheet_id}")
                store.set_sheet_enabled(sheet_id, body.enabled, mode="prod")
                return {"tool_id": tool_id, "sheet_id": sheet_id, "enabled_prod": body.enabled}
            if store.get_tool_catalog_row(tool_id) is None:
                raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_id}")
            registry.set_prod_enabled(tool_id, body.enabled)
            return {"tool_id": tool_id, "enabled_prod": body.enabled}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/tools-prod-status")
    def tools_prod_status() -> list[dict]:
        return [
            {"tool_id": tid, "name": name, "enabled": en, "enabled_prod": ep}
            for tid, name, en, ep in registry.list_tools_with_prod()
        ]

    @app.get("/runs")
    def runs(limit: int = 50, tool_id: str | None = None) -> list[dict]:
        return SQLiteManagementStore(db_path).list_tool_run_rows(limit=limit, tool_id=tool_id)

    @app.get("/usage/summary")
    def usage_summary(days: int = 30) -> list[dict]:
        return SQLiteManagementStore(db_path).usage_summary(days=days)

    @app.post("/tools/runs/log")
    def log_module_run(body: dict) -> dict:
        plugin_id = body.get("plugin_id", "")
        if not plugin_id:
            raise HTTPException(status_code=400, detail="plugin_id required")
        run_id = SQLiteManagementStore(db_path).log_module_execution(
            plugin_id=plugin_id,
            sheet_id=body.get("sheet_id"),
            success=bool(body.get("success", True)),
            duration_ms=body.get("duration_ms"),
            actor=body.get("actor", "user"),
        )
        return {"ok": True, "run_id": run_id}

    @app.post("/tools/{tool_id}/start", response_model=ToolStartResponse)
    def start_tool(tool_id: str) -> ToolStartResponse:
        try:
            tool = registry.get(tool_id)
            return manager.start(tool)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_id}") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=f"Tool script missing: {exc}") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/tools/{tool_id}/preview/start")
    def preview_start(tool_id: str) -> dict:
        try:
            tool = registry.get(tool_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            return manager.start_preview(tool)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.delete("/tools/preview/stop")
    def preview_stop() -> dict:
        manager.stop_preview()
        return {"ok": True}

    @app.get("/tools/preview/status")
    def preview_status_route() -> dict:
        return manager.preview_status()

    @app.get("/tools/active/status")
    def active_tool_status() -> dict:
        tool_id = manager._tool_id
        if not tool_id:
            return {"active": False}

        if manager._external_process is not None:
            alive = manager._external_process.poll() is None
            ready = bool(manager._external_ready_file and manager._external_ready_file.exists())
            return {
                "active": True,
                "tool_id": tool_id,
                "category": "external",
                "input_alive": alive,
                "output_alive": alive,
                "result_mtime": -1,
                "pid": manager._external_process.pid,
                "ready": ready,
                "run_id": manager._external_run_id,
                "started_at": manager._external_started_at,
                "log_path": str(manager._external_log_path) if manager._external_log_path else None,
                "ready_file": str(manager._external_ready_file) if manager._external_ready_file else None,
            }

        # Sheet tool: report per-tab result mtimes
        if manager._sheet_tab_info:
            sheet_id = tool_id[len("sheet-"):]
            tab_mtimes: dict[str, float] = {}
            tab_ready: dict[str, bool] = {}
            tab_urls: dict[str, dict[str, str]] = {}
            all_alive = True
            for tab in manager._sheet_tab_info:
                pid = tab["plugin_id"]
                tab_ready[pid] = bool(tab.get("ready", False))
                if tab.get("ready"):
                    tab_urls[pid] = {
                        "input_url": tab.get("input_url", ""),
                        "output_url": tab.get("output_url", ""),
                    }
                rf = manager._log_dir / f"sheet_{sheet_id}_{pid}_result.json"
                try:
                    tab_mtimes[pid] = rf.stat().st_mtime
                except FileNotFoundError:
                    tab_mtimes[pid] = -1
                procs = manager._sheet_processes.get(pid)
                if procs is not None:
                    in_p, out_p = procs
                    if in_p.poll() is not None or out_p.poll() is not None:
                        all_alive = False
            return {
                "active": True,
                "tool_id": tool_id,
                "input_alive": all_alive,
                "output_alive": all_alive,
                "result_mtime": -1,
                "run_id": manager._run_id,
                "sheet_tab_mtimes": tab_mtimes,
                "sheet_tab_ready": tab_ready,
                "sheet_tab_urls": tab_urls,
            }

        # App tool: a single self-contained Streamlit process (see _start_app).
        # Only _input_process exists (no output pane), so report its liveness for
        # both input/output — mirroring the single-process 'external' branch above.
        # Without this, the fall-through "Regular tool" branch reads output_alive
        # from the never-spawned _output_process and falsely reports it dead.
        if _derive_category(tool_id) == "app":
            alive = (
                manager._input_process is not None
                and manager._input_process.poll() is None
            )
            in_port = manager._input_port
            return {
                "active": True,
                "tool_id": tool_id,
                "category": "app",
                "input_alive": alive,
                "output_alive": alive,
                "result_mtime": -1,
                "run_id": manager._run_id,
                "input_url": f"http://127.0.0.1:{in_port}" if in_port else "",
                "output_url": f"http://127.0.0.1:{in_port}" if in_port else "",
            }

        # Regular tool
        input_alive = (
            manager._input_process is not None
            and manager._input_process.poll() is None
        )
        output_alive = (
            manager._output_process is not None
            and manager._output_process.poll() is None
        )
        result_file = manager._log_dir / f"{tool_id}_result.json"
        try:
            result_mtime = result_file.stat().st_mtime
        except FileNotFoundError:
            result_mtime = -1
        in_port = manager._input_port
        out_port = manager._output_port
        return {
            "active": True,
            "tool_id": tool_id,
            "input_alive": input_alive,
            "output_alive": output_alive,
            "result_mtime": result_mtime,
            "run_id": manager._run_id,
            "input_url": f"http://127.0.0.1:{in_port}" if in_port else "",
            "output_url": f"http://127.0.0.1:{out_port}" if out_port else "",
        }

    @app.post("/tools/active/sheet-tab/{plugin_id}/start")
    def start_sheet_tab(plugin_id: str) -> dict:
        if not manager._sheet_tab_info:
            raise HTTPException(status_code=409, detail="No sheet tool is currently active")
        try:
            tab = manager._start_one_sheet_tab(plugin_id)
            return {
                "plugin_id": tab["plugin_id"],
                "input_url": tab["input_url"],
                "output_url": tab["output_url"],
                "input_port": tab["input_port"],
                "output_port": tab["output_port"],
                "ready": True,
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown sheet tab: {plugin_id}") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/tools/stop")
    def stop_tool() -> dict[str, str]:
        manager.stop()
        return {"status": "stopped"}

    @app.get("/selected-paths", response_model=SelectedPathsResponse)
    def get_selected_paths() -> SelectedPathsResponse:
        return SelectedPathsResponse(paths=selected_paths.get_paths())

    @app.post("/selected-paths", response_model=SelectedPathsResponse)
    def set_selected_paths(request: SelectedPathsRequest) -> SelectedPathsResponse:
        selected_paths.set_paths(request.paths)
        return SelectedPathsResponse(paths=selected_paths.get_paths())

    # ── External image bridge endpoints ──────────────────────────────────────

    class ExternalImageRequest(BaseModel):
        image_url: str
        metadata: dict = {}

    class ExternalLabelingToolRequest(BaseModel):
        image_url: str
        tool: str = "x-anylabeling"
        metadata: dict = {}

    @app.post("/external/open-xanylabeling")
    def external_open_xanylabeling(request: ExternalImageRequest) -> dict:
        queue_dir = log_dir / "external-queue"
        try:
            local_path = _ext_download_image(request.image_url, queue_dir)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"圖片下載失敗: {exc}") from exc
        try:
            _ext_launch_xanylabeling(local_path, log_dir)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"xanylabeling 啟動失敗: {exc}") from exc
        return {"status": "launched", "local_path": str(local_path)}

    @app.post("/external/open-labeling-tool")
    def external_open_labeling_tool(request: ExternalLabelingToolRequest) -> dict:
        queue_dir = log_dir / "external-queue"
        try:
            local_path = _ext_download_image(request.image_url, queue_dir)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"??銝?憭望?: {exc}") from exc
        try:
            _ext_launch_labeling_tool(request.tool, local_path, log_dir)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"{request.tool} ??憭望?: {exc}") from exc
        return {"status": "launched", "tool": request.tool, "local_path": str(local_path)}

    @app.post("/external/queue-image")
    def external_queue_image(request: ExternalImageRequest) -> dict:
        queue_dir = log_dir / "external-queue"
        try:
            local_path = _ext_download_image(request.image_url, queue_dir)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"圖片下載失敗: {exc}") from exc
        entry = {
            "id": uuid.uuid4().hex,
            "local_path": str(local_path),
            "original_url": request.image_url,
            "metadata": request.metadata,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
        with _ext_queue_lock:
            _ext_queue.append(entry)
        return {"id": entry["id"], "local_path": str(local_path), "queue_size": len(_ext_queue)}

    @app.get("/external/queue")
    def external_get_queue() -> dict:
        with _ext_queue_lock:
            return {"items": list(_ext_queue), "count": len(_ext_queue)}

    @app.delete("/external/queue/{item_id}")
    def external_dequeue(item_id: str) -> dict:
        with _ext_queue_lock:
            before = len(_ext_queue)
            _ext_queue[:] = [e for e in _ext_queue if e["id"] != item_id]
            removed = before - len(_ext_queue)
        if not removed:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"status": "removed", "queue_size": len(_ext_queue)}

    @app.post("/shutdown")
    def shutdown() -> dict[str, str]:
        manager.stop()

        def exit_later() -> None:
            logging.info("Sidecar shutdown requested")
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Timer(0.2, exit_later).start()
        return {"status": "shutting_down"}

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CIM Python sidecar")
    parser.add_argument("--control-port", type=int)
    parser.add_argument("--log-dir", type=Path, default=ROOT_DIR / "logs")
    parser.add_argument("--run-streamlit-script")
    parser.add_argument("--tool-port", type=int)
    parser.add_argument(
        "--rebuild-catalog",
        action="store_true",
        help="Delete the per-device tools.sqlite before boot so the catalog is "
             "rebuilt from scratch (plugin.yaml + sheet YAML + config/seed.yaml). "
             "Use after a git pull for a guaranteed-clean catalog.",
    )
    return parser.parse_args()


def _distribution_source_from_spec(spec: str):
    """Build a ToolDistributionSource from a CIM_DISTRIBUTION_SOURCE spec.

    Accepts ``local:<dir>``, a bare path (→ local), or ``http(s)://<host>`` (→
    the registry server). See docs/platform/fleet-distribution.md.
    """
    from core.distribution import HttpRegistrySource, LocalFsSource, get_secret  # noqa: PLC0415

    secret = get_secret()
    if spec.startswith(("http://", "https://")):
        return HttpRegistrySource(spec, secret=secret)
    if spec.startswith("local:"):
        spec = spec[len("local:"):]
    return LocalFsSource(Path(spec).expanduser(), secret=secret)


def _artifact_tool_name(artifact) -> str:
    """Best-effort display name from an artifact's bundled plugin.yaml."""
    try:
        import yaml  # noqa: PLC0415

        meta = yaml.safe_load(artifact.content.get("plugin.yaml", "")) or {}
        return str(meta.get("name") or artifact.tool_id)
    except Exception:
        return artifact.tool_id


def pull_distribution_into_catalog(db_path: Path, source_spec: str,
                                   channel: str = "prod") -> dict:
    """Fleet distribution (#1): pull centrally-approved tool artifacts from a
    distribution source into THIS device's local catalog.

    Each ``fetch`` verifies the artifact signature, so tampered/unsigned code is
    rejected before it can be published locally. env-gated by
    ``CIM_DISTRIBUTION_SOURCE`` (a no-op when unset), so default single-machine
    behaviour is unchanged. Never raises — a broken source or a single bad
    artifact must not block engine startup. Returns a small report dict.
    See docs/platform/fleet-distribution.md.
    """
    store = SQLiteManagementStore(db_path)
    pulled: list[str] = []
    skipped: list[str] = []
    try:
        source = _distribution_source_from_spec(source_spec)
        metas = source.list_artifacts(channel)
    except Exception as exc:  # source unreachable / misconfigured
        logging.warning("Distribution source unavailable (%s): %s", source_spec, exc)
        return {"pulled": pulled, "skipped": skipped, "error": str(exc)}

    for meta in metas:
        ref = f"{meta.tool_id}@{meta.version}"
        try:
            artifact = source.fetch(meta.tool_id, meta.version)  # verifies signature
            content_json = json.dumps(artifact.content, ensure_ascii=False)
            store.publish_tool_snapshot(
                artifact.tool_id,
                _artifact_tool_name(artifact),
                artifact.version,
                content_json,
                changelog=f"distribution:{channel}",
                author=artifact.author or "registry",
            )
            pulled.append(ref)
        except Exception as exc:  # bad signature / write error — skip, don't abort
            logging.warning("Skip distribution artifact %s: %s", ref, exc)
            skipped.append(ref)

    if pulled:
        logging.info("Pulled %d tool(s) from %s into catalog: %s",
                     len(pulled), source_spec, pulled)
    return {"pulled": pulled, "skipped": skipped}


def main() -> None:
    args = parse_args()
    if args.run_streamlit_script:
        if not args.tool_port:
            raise SystemExit("--tool-port is required with --run-streamlit-script")
        run_streamlit_script(args.run_streamlit_script, args.tool_port)
        return

    if not args.control_port:
        raise SystemExit("--control-port is required")

    configure_logging(args.log_dir)
    # Early submodule guard: if labeling/AI4BI submodules weren't checked out,
    # log a loud, pasteable [CIM-PREFLIGHT] error (does not exit — see docstring).
    preflight_submodules()
    os.environ["CIM_CONTROL_PORT"] = str(args.control_port)
    db_path = resolve_tools_db_path(args.log_dir)
    # --rebuild-catalog: drop the per-device derived cache so the catalog is
    # rebuilt cleanly from the declarative sources on this boot. Safe because
    # tools.sqlite holds no authoritative state (runtime logs aside, which a
    # fresh rebuild simply omits). Handy right after a git pull.
    if getattr(args, "rebuild_catalog", False) and db_path.exists():
        try:
            db_path.unlink()
            logging.info("[CIM-BOOT] --rebuild-catalog: removed %s (will rebuild)", db_path)
        except OSError as exc:
            logging.error("[CIM-BOOT] --rebuild-catalog: failed to remove %s: %s", db_path, exc)
    # Boot banner: makes "which code/DB is this engine actually running?" visible
    # at a glance (grep [CIM-BOOT]). boot_id changes every restart, so you can
    # confirm a fresh process picked up your fix.
    logging.info("[CIM-BOOT] engine commit=%s boot_id=%s db=%s",
                 engine_commit(), _BOOT_ID, db_path)
    os.environ["CIM_TOOLS_DB"] = str(db_path)
    selected_paths = SelectedPathStore(args.log_dir / "selected_paths.json")
    registry = ToolRegistry(SQLiteToolAdapter(db_path))
    # Fleet distribution (#1): when CIM_DISTRIBUTION_SOURCE is set, pull
    # centrally-approved (signed) tool artifacts into this device's catalog.
    # Unset → no-op, so single-machine behaviour is unchanged.
    _dist_source = os.environ.get("CIM_DISTRIBUTION_SOURCE", "").strip()
    if _dist_source:
        pull_distribution_into_catalog(db_path, _dist_source)
    manager = ToolProcessManager(args.log_dir, args.log_dir / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path, args.log_dir)
    uvicorn.run(app, host="127.0.0.1", port=args.control_port, log_level="info")


if __name__ == "__main__":
    main()
