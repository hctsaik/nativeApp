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
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


ROOT_DIR = resource_root()
TOOLS_DIR = ROOT_DIR / "tools"


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


class SheetTabInfo(BaseModel):
    plugin_id: str
    label: str
    input_url: str
    output_url: str
    input_port: int
    output_port: int


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


class SelectedPathsRequest(BaseModel):
    paths: list[str]


class SelectedPathsResponse(BaseModel):
    paths: list[str]


class ToolAdapter(ABC):
    @abstractmethod
    def list_tools(self) -> list[ToolDefinition]:
        raise NotImplementedError

    @abstractmethod
    def get_tool(self, tool_id: str) -> ToolDefinition:
        raise NotImplementedError


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
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
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
            # ── Auto-register modules from plugin.yaml (source of truth) ────────
            self._scan_and_register_plugins(connection)

            # ── Static seeds: sheet tools + management + external (no plugin.yaml) ─
            connection.executemany(
                """
                INSERT OR IGNORE INTO tools (
                    tool_id, name, script_relative_path, version,
                    signature, source_commit, author, approved_at, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("sheet-edge-analysis", "邊緣品質分析（套件）", "sheet_runner.py",
                     "1.0.0", None, "seed", "system", None, 1),
                    ("sheet-共用標註功能_-_套件", "共用標註功能 - 套件", "sheet_runner.py",
                     "1.0.0", None, "seed", "system", None, 1),
                    ("sheet-annotation_workflow", "標注工作流", "sheet_runner.py",
                     "1.0.0", None, "seed", "system", None, 1),
                    ("management-center", "管理中心", "management_runner.py",
                     "1.0.0", None, "seed", "system", None, 1),
                    ("labelme-dino", "LabelMe Dino", "external_labelme_dino",
                     "0.1.0", None, "seed", "system", None, 1),
                ],
            )
            # Disable legacy tools no longer in the product
            connection.execute(
                "UPDATE tools SET enabled = 0 WHERE tool_id IN (?, ?, ?, ?)",
                ("sample-csv", "workflow-edge-analysis", "module_007", "placeholder"),
            )
            # Ensure all static-seed active tools are prod-enabled
            connection.execute(
                "UPDATE tools SET enabled_prod = 1 WHERE tool_id IN (?, ?, ?, ?, ?)",
                ("sheet-edge-analysis", "sheet-共用標註功能_-_套件", "sheet-annotation_workflow",
                 "management-center", "labelme-dino"),
            )
            # migration: add module_014/015/016 to annotation_workflow
            for tab_order, plugin_id, label in [
                (3, "module_014", "📤 Export"),
                (4, "module_015", "📊 Dashboard"),
                (5, "module_016", "🤖 AI Pre-labeling"),
                (6, "module_017", "🏷️ Label Manager"),
                (7, "module_018", "🖼️ Review Gallery"),
            ]:
                try:
                    connection.execute(
                        "INSERT OR IGNORE INTO sheet_tabs (sheet_id, tab_order, plugin_id, label)"
                        " VALUES (?, ?, ?, ?)",
                        ("annotation_workflow", tab_order, plugin_id, label),
                    )
                except Exception:
                    pass

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
        scripts_dir = ROOT_DIR / "scripts"
        for yaml_path in sorted(scripts_dir.glob("*/plugin.yaml")):
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

            connection.execute(
                """
                INSERT OR IGNORE INTO tools (
                    tool_id, name, script_relative_path, version,
                    source_commit, author, enabled, vendor, domain, deprecated_at
                ) VALUES (?, ?, ?, ?, 'plugin.yaml', ?, ?, ?, ?, ?)
                """,
                (tool_id, name, script, version, author, enabled, vendor, domain, deprecated_at),
            )
            # Sync mutable fields from yaml on every startup
            connection.execute(
                """
                UPDATE tools
                SET name=?, script_relative_path=?, version=?, enabled=?,
                    enabled_prod=?, vendor=?, domain=?, deprecated_at=?
                WHERE tool_id=?
                """,
                (name, script, version, enabled, enabled, vendor, domain, deprecated_at, tool_id),
            )

    def list_tools(self) -> list[ToolDefinition]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT tool_id, name, script_relative_path, version, signature,
                       source_commit, author, approved_at
                FROM tools
                WHERE enabled = 1
                ORDER BY order_index, name
                """
            ).fetchall()
        return [self._row_to_tool(row) for row in rows]

    def set_prod_enabled(self, tool_id: str, enabled: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE tools SET enabled_prod = ? WHERE tool_id = ?",
                (1 if enabled else 0, tool_id),
            )

    def list_tools_with_prod(self) -> list[tuple]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT tool_id, name, enabled, enabled_prod FROM tools ORDER BY name"
            ).fetchall()
        return [(r["tool_id"], r["name"], bool(r["enabled"]), bool(r["enabled_prod"])) for r in rows]

    def get_tool(self, tool_id: str) -> ToolDefinition:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT tool_id, name, script_relative_path, version, signature,
                       source_commit, author, approved_at
                FROM tools
                WHERE tool_id = ? AND enabled = 1
                """,
                (tool_id,),
            ).fetchone()
        if row is None:
            raise KeyError(tool_id)
        return self._row_to_tool(row)

    def _row_to_tool(self, row: sqlite3.Row) -> ToolDefinition:
        return ToolDefinition(
            tool_id=row["tool_id"],
            name=row["name"],
            script_path=TOOLS_DIR / row["script_relative_path"],
            version=row["version"],
            signature=row["signature"],
            source_commit=row["source_commit"],
            author=row["author"],
            approved_at=row["approved_at"],
        )


def _derive_category(tool_id: str) -> str:
    if tool_id == "labelme-dino":
        return "external"
    if tool_id.startswith("sheet-"):
        return "sheet"
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
            )
            for tool in self._adapter.list_tools()
        ]

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


class ToolProcessManager:
    def __init__(self, log_dir: Path, selected_paths_file: Path) -> None:
        import threading
        self._lock = threading.RLock()
        self._log_dir = log_dir.resolve()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._selected_paths_file = selected_paths_file.resolve()
        self._input_process: Optional[subprocess.Popen] = None
        self._output_process: Optional[subprocess.Popen] = None
        self._external_process: Optional[subprocess.Popen] = None
        self._external_log_file = None
        self._external_log_path: Optional[Path] = None
        self._external_ready_file: Optional[Path] = None
        self._external_run_id: Optional[str] = None
        self._external_started_at: Optional[float] = None
        self._external_last_probe: Optional[dict] = None
        self._sheet_processes: list[tuple[subprocess.Popen, subprocess.Popen]] = []
        self._sheet_tab_info: list[dict] = []
        self._tool_id: Optional[str] = None

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
        env["CIM_TOOLS_DB"] = str(ROOT_DIR / "config" / "tools.sqlite")
        # Inject connector credentials from secrets file (never stored in DB or YAML)
        secrets_path = self._log_dir / "secrets" / "connector_creds.json"
        if secrets_path.exists():
            try:
                import json as _json
                creds = _json.loads(secrets_path.read_text(encoding="utf-8"))
                env["CIM_CONNECTOR_DSN"]      = creds.get("dsn", "")
                env["CIM_CONNECTOR_TOKEN"]    = creds.get("token", "")
                env["CIM_CONNECTOR_BASE_URL"] = creds.get("base_url", "")
            except Exception:
                pass
        return env

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
        db_path = ROOT_DIR / "config" / "tools.sqlite"
        def _query_tabs() -> list[dict]:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT plugin_id, label FROM sheet_tabs WHERE sheet_id = ? ORDER BY tab_order",
                    (sheet_id,),
                ).fetchall()
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
                status = {"active": True, "tool_id": self._tool_id, "category": "module"}
        return {
            "ok": True,
            "sidecar_pid": os.getpid(),
            "root_dir": str(ROOT_DIR),
            "log_dir": str(self._log_dir),
            "active_tool": status,
            "runtime": self.runtime_status(),
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
        self._external_started_at = time.time()
        ready_payload = self._wait_for_ready_file(ready_file)
        if not ready_payload.get("ok", False):
            self.stop()
            raise RuntimeError(f"video_annotator did not become ready: {ready_payload.get('error', 'unknown error')}")
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

        input_port = find_free_port()
        output_port = find_free_port(exclude={input_port})

        self._input_process = self._spawn(input_script, tool, input_port, "input")
        self._output_process = self._spawn(output_script, tool, output_port, "output")
        self._tool_id = tool.tool_id

        if not wait_for_port(input_port):
            self.stop()
            raise RuntimeError(f"Streamlit input for {tool.tool_id} did not become ready in time")
        if not wait_for_port(output_port):
            self.stop()
            raise RuntimeError(f"Streamlit output for {tool.tool_id} did not become ready in time")

        return ToolStartResponse(
            tool_id=tool.tool_id,
            input_url=f"http://127.0.0.1:{input_port}",
            output_url=f"http://127.0.0.1:{output_port}",
            input_port=input_port,
            output_port=output_port,
            category=_derive_category(tool.tool_id),
        )

    def _start_sheet(self, tool: ToolDefinition) -> ToolStartResponse:
        sheet_id = tool.tool_id[len("sheet-"):]
        tabs = self._get_sheet_tabs(sheet_id)
        if not tabs:
            return self._start_regular(tool)

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

            in_proc = self._spawn(input_script, tool, in_port, "input", plugin_id)
            out_proc = self._spawn(output_script, tool, out_port, "output", plugin_id)
            self._sheet_processes.append((in_proc, out_proc))

            tab_info.append({
                "plugin_id": plugin_id,
                "label": tab["label"],
                "input_port": in_port,
                "output_port": out_port,
                "input_url": f"http://127.0.0.1:{in_port}",
                "output_url": f"http://127.0.0.1:{out_port}",
            })

        # Wait for all processes
        for t in tab_info:
            if not wait_for_port(t["input_port"]):
                self.stop()
                raise RuntimeError(f"Sheet tab {t['plugin_id']} input did not become ready in time")
            if not wait_for_port(t["output_port"]):
                self.stop()
                raise RuntimeError(f"Sheet tab {t['plugin_id']} output did not become ready in time")

        self._sheet_tab_info = tab_info
        self._tool_id = tool.tool_id

        first = tab_info[0]
        return ToolStartResponse(
            tool_id=tool.tool_id,
            input_url=first["input_url"],
            output_url=first["output_url"],
            input_port=first["input_port"],
            output_port=first["output_port"],
            category="sheet",
            sheet_tabs=[SheetTabInfo(**t) for t in tab_info],
        )

    def stop(self) -> None:
        with self._lock:
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
            for i, (in_p, out_p) in enumerate(self._sheet_processes):
                _terminate_process(in_p, f"{self._tool_id}-sheet-{i}-input")
                _terminate_process(out_p, f"{self._tool_id}-sheet-{i}-output")
            self._sheet_processes = []
            self._sheet_tab_info = []
            self._tool_id = None


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


def create_app(manager: ToolProcessManager, registry: ToolRegistry, selected_paths: SelectedPathStore) -> FastAPI:
    app = FastAPI(title="CIM Python Sidecar", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/version")
    def version() -> dict:
        return {
            "name": "CIM Python Sidecar",
            "version": app.version,
            "root_dir": str(ROOT_DIR),
            "pid": os.getpid(),
        }

    @app.get("/runtime")
    def runtime() -> dict:
        return manager.runtime_status()

    @app.get("/diagnostics")
    def diagnostics() -> dict:
        return manager.diagnostics()

    @app.get("/tools", response_model=list[ToolInfo])
    def tools() -> list[ToolInfo]:
        all_tools = registry.list_tools()
        if os.environ.get("CIM_DEV_MODE", "1") != "1":
            all_tools = [t for t in all_tools if t.category != "management"]
            prod_rows = registry.list_tools_with_prod()
            prod_enabled = {tool_id for tool_id, _, _, ep in prod_rows if ep}
            all_tools = [t for t in all_tools if t.tool_id in prod_enabled]
        return all_tools

    class ProdEnabledRequest(BaseModel):
        enabled: bool

    @app.patch("/tools/{tool_id}/prod-enabled")
    def set_prod_enabled(tool_id: str, body: ProdEnabledRequest) -> dict:
        try:
            registry.set_prod_enabled(tool_id, body.enabled)
            return {"tool_id": tool_id, "enabled_prod": body.enabled}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/tools-prod-status")
    def tools_prod_status() -> list[dict]:
        return [
            {"tool_id": tid, "name": name, "enabled": en, "enabled_prod": ep}
            for tid, name, en, ep in registry.list_tools_with_prod()
        ]

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
            all_alive = True
            for i, (tab, (in_p, out_p)) in enumerate(zip(manager._sheet_tab_info, manager._sheet_processes)):
                pid = tab["plugin_id"]
                rf = manager._log_dir / f"sheet_{sheet_id}_{pid}_result.json"
                try:
                    tab_mtimes[pid] = rf.stat().st_mtime
                except FileNotFoundError:
                    tab_mtimes[pid] = -1
                if in_p.poll() is not None or out_p.poll() is not None:
                    all_alive = False
            return {
                "active": True,
                "tool_id": tool_id,
                "input_alive": all_alive,
                "output_alive": all_alive,
                "result_mtime": -1,
                "sheet_tab_mtimes": tab_mtimes,
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
        return {
            "active": True,
            "tool_id": tool_id,
            "input_alive": input_alive,
            "output_alive": output_alive,
            "result_mtime": result_mtime,
        }

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
    return parser.parse_args()


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
    os.environ["CIM_CONTROL_PORT"] = str(args.control_port)
    selected_paths = SelectedPathStore(args.log_dir / "selected_paths.json")
    registry = ToolRegistry(SQLiteToolAdapter(ROOT_DIR / "config" / "tools.sqlite"))
    manager = ToolProcessManager(args.log_dir, args.log_dir / "selected_paths.json")
    app = create_app(manager, registry, selected_paths)
    uvicorn.run(app, host="127.0.0.1", port=args.control_port, log_level="info")


if __name__ == "__main__":
    main()
