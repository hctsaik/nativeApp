from __future__ import annotations

import os
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

_ENGINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ENGINE_DIR))

from management_insights import (  # noqa: E402
    IntegrityIssue,
    collect_dashboard_summary,
    collect_integrity_issues,
    collect_tool_readiness,
    module_preflight,
    module_snapshot_diff,
    validate_sheet_references,
    validate_sheet_prod_readiness,
)
from auth_provider import AuthProvider  # noqa: E402
from management_store import SQLiteManagementStore  # noqa: E402
from management_package_importer import ModulePackageError  # noqa: E402
from management_use_cases import ManagementUseCases, SheetProdReadinessError  # noqa: E402
from plugin_registry import PluginRegistry, _is_dev_mode  # noqa: E402

LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
_DB_PATH = Path(os.environ.get("CIM_TOOLS_DB", str(LOG_DIR / "data" / "tools.sqlite")))
_SCRIPTS_DIR = _ENGINE_DIR / "scripts"
_LAYER = os.environ.get("CIM_TOOL_LAYER", "input")
_CONTROL_PORT = os.environ.get("CIM_CONTROL_PORT", "")


def _registry() -> PluginRegistry:
    return PluginRegistry(db_path=_DB_PATH, scripts_dir=_SCRIPTS_DIR)


def _store() -> SQLiteManagementStore:
    return SQLiteManagementStore(_DB_PATH)


def _use_cases(reg: PluginRegistry) -> ManagementUseCases:
    return ManagementUseCases(_DB_PATH, _SCRIPTS_DIR, reg, _store())


def _actor() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "admin"


def _current_role() -> str:
    return AuthProvider(db_path=_DB_PATH).get_current_role()


def _can_manage() -> bool:
    return _current_role() == "admin"


def _management_backend() -> str:
    explicit = (
        os.environ.get("CIM_MANAGEMENT_BACKEND")
        or os.environ.get("CIM_DB_BACKEND")
        or os.environ.get("CIM_DATABASE_BACKEND")
    )
    if explicit:
        return explicit.strip().lower()
    if os.environ.get("CIM_ORACLE_DSN") or os.environ.get("ORACLE_DSN"):
        return "oracle"
    return "sqlite"


def _audit(reg: PluginRegistry, action: str, target_type: str, target_id: str, **details) -> None:
    try:
        reg.record_audit_event(
            action=action,
            target_type=target_type,
            target_id=target_id,
            actor=_actor(),
            details=details,
        )
    except Exception:
        pass


def _category_badge(tool_id: str) -> str:
    if tool_id.startswith("sheet_") or tool_id.startswith("sheet-"):
        return "Sheet"
    if tool_id.startswith("management-"):
        return "Management"
    return "Module"


def _load_tool_rows() -> list[dict[str, Any]]:
    return _store().list_visible_tool_rows()


def _load_archived_rows() -> list[dict[str, Any]]:
    return _store().list_archived_tool_rows()


def _set_tool_enabled(tool_id: str, enabled: bool) -> None:
    _store().set_tool_enabled(tool_id, enabled)


def _start_tool(tool_id: str) -> None:
    req = urllib.request.Request(
        f"http://127.0.0.1:{_CONTROL_PORT}/tools/{urllib.parse.quote(tool_id)}/start",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=b"",
    )
    with urllib.request.urlopen(req, timeout=30):
        pass


def _get_active_tool() -> dict | None:
    if not _CONTROL_PORT:
        return None
    try:
        import json as _json  # noqa: PLC0415
        with urllib.request.urlopen(
            f"http://127.0.0.1:{_CONTROL_PORT}/tools/active/status", timeout=2
        ) as resp:
            return _json.loads(resp.read())
    except Exception:
        return None


def _get_preview_status() -> dict | None:
    if not _CONTROL_PORT:
        return None
    try:
        import json as _json  # noqa: PLC0415
        with urllib.request.urlopen(
            f"http://127.0.0.1:{_CONTROL_PORT}/tools/preview/status", timeout=2
        ) as resp:
            return _json.loads(resp.read())
    except Exception:
        return None


def _start_preview(tool_id: str) -> dict:
    import json as _json  # noqa: PLC0415
    req = urllib.request.Request(
        f"http://127.0.0.1:{_CONTROL_PORT}/tools/{urllib.parse.quote(tool_id)}/preview/start",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=b"",
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        return _json.loads(resp.read())


def _stop_preview() -> None:
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{_CONTROL_PORT}/tools/preview/stop",
            method="DELETE",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:
        pass


def _control_get_json(path: str, timeout: float = 3.0) -> dict | None:
    if not _CONTROL_PORT:
        return None
    try:
        import json as _json  # noqa: PLC0415
        with urllib.request.urlopen(f"http://127.0.0.1:{_CONTROL_PORT}{path}", timeout=timeout) as resp:
            return _json.loads(resp.read())
    except Exception:
        return None


def _publish_to_prod(
    reg: PluginRegistry,
    plugin_id: str,
    tool_id: str,
    changelog: str,
    author: str,
    diff_summary: dict,
) -> str:
    """One-click: publish plugin version + enable prod in both tables."""
    result = _use_cases(reg).publish_tool_to_prod(
        plugin_id,
        tool_id,
        changelog=changelog,
        author=author,
        actor=_actor(),
        diff_summary=diff_summary,
    )
    return result.version_id


def _create_snapshot(
    reg: PluginRegistry,
    plugin_id: str,
    tool_id: str,
    changelog: str,
    author: str,
) -> str:
    result = _use_cases(reg).create_snapshot_from_filesystem(
        plugin_id,
        tool_id,
        changelog=changelog,
        author=author,
        actor=_actor(),
    )
    return result.version_id


# ── Publish modal dialog ─────────────────────────────────────────────────────


@st.dialog("Publish Snapshot")
def _publish_dialog(reg: PluginRegistry, plugin_id: str, tool_id: str) -> None:
    preflight = module_preflight(_SCRIPTS_DIR, plugin_id)
    snapshot_diff = module_snapshot_diff(_SCRIPTS_DIR, _DB_PATH, plugin_id)

    if not preflight.ok:
        st.error("Publish checks failed. Fix these issues before creating a snapshot.")
        for issue in preflight.issues:
            st.caption(f"- {issue}")
        if st.button("Close", key="dialog_close_prefail"):
            st.rerun()
        return

    st.caption(
        f"**{tool_id}**: {len(snapshot_diff.added)} added, "
        f"{len(snapshot_diff.changed)} changed, {len(snapshot_diff.removed)} removed."
    )
    st.info("This creates a new active snapshot and makes the module visible in Prod.")
    default_author = st.session_state.get("publish_author", os.environ.get("USERNAME") or "admin")
    changelog = st.text_area(
        "Changelog",
        placeholder="Describe what changed in this snapshot.",
        height=100,
        key=f"dialog_changelog_{plugin_id}",
    )
    author = st.text_input("Author", value=default_author, key=f"dialog_author_{plugin_id}")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button(
            "Publish snapshot and enable Prod",
            type="primary",
            disabled=not (changelog.strip() and author.strip()),
            use_container_width=True,
            key=f"dialog_confirm_{plugin_id}",
        ):
            try:
                vid = _publish_to_prod(
                    reg,
                    plugin_id,
                    tool_id,
                    changelog=changelog.strip(),
                    author=author.strip(),
                    diff_summary=snapshot_diff.summary(),
                )
                st.session_state["publish_author"] = author.strip()
                st.toast(f"Published snapshot #{vid}; Prod visibility is on.", icon=":material/check_circle:")
                st.rerun()
            except Exception as exc:
                st.error(f"Publish failed: {exc}")
    with col_cancel:
        if st.button("Cancel", use_container_width=True, key=f"dialog_cancel_{plugin_id}"):
            st.rerun()


@st.dialog("Create Snapshot")
def _create_snapshot_dialog(reg: PluginRegistry, plugin_id: str, tool_id: str) -> None:
    preflight = module_preflight(_SCRIPTS_DIR, plugin_id)
    snapshot_diff = module_snapshot_diff(_SCRIPTS_DIR, _DB_PATH, plugin_id)

    if not preflight.ok:
        st.error("Publish checks failed. Fix these issues before creating a snapshot.")
        for issue in preflight.issues:
            st.caption(f"- {issue}")
        if st.button("Close", key="dialog_close_create_snapshot_prefail"):
            st.rerun()
        return

    st.caption(
        f"**{tool_id}**: {len(snapshot_diff.added)} added, "
        f"{len(snapshot_diff.changed)} changed, {len(snapshot_diff.removed)} removed."
    )
    st.info("This creates an active snapshot. Prod visibility stays off until you release it.")
    default_author = st.session_state.get("publish_author", os.environ.get("USERNAME") or "admin")
    changelog = st.text_area(
        "Changelog",
        placeholder="Describe what changed in this snapshot.",
        height=100,
        key=f"dialog_snapshot_changelog_{plugin_id}",
    )
    author = st.text_input("Author", value=default_author, key=f"dialog_snapshot_author_{plugin_id}")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button(
            "Create snapshot",
            type="primary",
            disabled=not (changelog.strip() and author.strip()),
            use_container_width=True,
            key=f"dialog_snapshot_confirm_{plugin_id}",
        ):
            try:
                vid = _create_snapshot(reg, plugin_id, tool_id, changelog.strip(), author.strip())
                st.session_state["publish_author"] = author.strip()
                st.toast(f"Created snapshot #{vid}. Prod visibility is unchanged.", icon=":material/check_circle:")
                st.rerun()
            except Exception as exc:
                st.error(f"Snapshot failed: {exc}")
    with col_cancel:
        if st.button("Cancel", use_container_width=True, key=f"dialog_snapshot_cancel_{plugin_id}"):
            st.rerun()
        return

    st.caption(
        f"**{tool_id}** · Compared with the active snapshot: "
        f"{len(snapshot_diff.added)} added, "
        f"{len(snapshot_diff.changed)} changed, "
        f"{len(snapshot_diff.removed)} removed."
    )
    st.info("This creates a new active snapshot and makes the module visible in Prod.")
    default_author = st.session_state.get("publish_author", os.environ.get("USERNAME") or "admin")
    changelog = st.text_area(
        "Changelog",
        placeholder="Describe what changed in this snapshot.",
        height=100,
        key=f"dialog_changelog_{plugin_id}",
    )
    author = st.text_input(
        "Author",
        value=default_author,
        key=f"dialog_author_{plugin_id}",
    )
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button(
            "Publish snapshot and enable Prod",
            type="primary",
            disabled=not (changelog.strip() and author.strip()),
            use_container_width=True,
            key=f"dialog_confirm_{plugin_id}",
        ):
            try:
                vid = _publish_to_prod(
                    reg,
                    plugin_id,
                    tool_id,
                    changelog=changelog.strip(),
                    author=author.strip(),
                    diff_summary=snapshot_diff.summary(),
                )
                st.session_state["publish_author"] = author.strip()
                st.toast(f"Published snapshot #{vid}; Prod visibility is on.", icon=":material/check_circle:")
                st.rerun()
            except Exception as exc:
                st.error(f"Publish failed: {exc}")
    with col_cancel:
        if st.button("Cancel", use_container_width=True, key=f"dialog_cancel_{plugin_id}"):
            st.rerun()


@st.dialog("Confirm Rollback")
def _confirm_rollback_dialog(reg: PluginRegistry, plugin_id: str, version_id: int) -> None:
    st.warning("Rollback changes the active snapshot used by Prod.")
    st.caption(f"Target: `{plugin_id}` snapshot #{version_id}")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Rollback", type="primary", key=f"confirm_rollback_{plugin_id}_{version_id}"):
            _use_cases(reg).rollback_tool_version(plugin_id, version_id, actor=_actor())
            st.toast(f"Rolled back to snapshot #{version_id}", icon=":material/check_circle:")
            st.rerun()
    with col_cancel:
        if st.button("Cancel", key=f"cancel_rollback_{plugin_id}_{version_id}"):
            st.rerun()


@st.dialog("Confirm Archive")
def _confirm_archive_dialog(reg: PluginRegistry, tool_id: str, name: str) -> None:
    st.warning("Archiving hides this tool from the Portal. Prod visibility and snapshots are not deleted.")
    st.caption(f"Target: **{name}** `{tool_id}`")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Archive tool", type="primary", key=f"confirm_archive_{tool_id}"):
            _set_tool_enabled(tool_id, False)
            _audit(reg, "archive", "tool", tool_id)
            st.toast(f"Archived {name}.", icon=":material/archive:")
            st.rerun()
    with col_cancel:
        if st.button("Cancel", key=f"cancel_archive_{tool_id}"):
            st.rerun()


@st.dialog("Confirm Restore")
def _confirm_restore_dialog(reg: PluginRegistry, tool_id: str, name: str) -> None:
    st.info("Restoring makes this tool visible in the Portal again.")
    st.caption(f"Target: **{name}** `{tool_id}`")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Restore tool", type="primary", key=f"confirm_restore_{tool_id}"):
            _set_tool_enabled(tool_id, True)
            _audit(reg, "restore", "tool", tool_id)
            st.toast(f"Restored {name}.", icon=":material/unarchive:")
            st.rerun()
    with col_cancel:
        if st.button("Cancel", key=f"cancel_restore_{tool_id}"):
            st.rerun()


@st.dialog("Confirm Delete Draft")
def _confirm_delete_draft_tool_dialog(reg: PluginRegistry, tool_id: str, name: str) -> None:
    st.warning("Deleting a draft removes the tool catalog row only. Source files are not deleted.")
    st.caption("Allowed only when the tool has no snapshots, is not visible in Prod, and is not referenced by Sheets.")
    st.caption(f"Target: **{name}** `{tool_id}`")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Delete draft", type="primary", key=f"confirm_delete_draft_{tool_id}"):
            try:
                _use_cases(reg).delete_draft_tool(tool_id, actor=_actor())
                st.toast(f"Deleted draft {name}.", icon=":material/delete:")
                st.rerun()
            except Exception as exc:
                st.error(f"Delete draft failed: {exc}")
    with col_cancel:
        if st.button("Cancel", key=f"cancel_delete_draft_{tool_id}"):
            st.rerun()


@st.dialog("Confirm Sheet Delete")
def _confirm_delete_sheet_dialog(reg: PluginRegistry, sheet_id: str, name: str) -> None:
    st.warning("Deleting a Sheet removes its tab composition. This does not delete module snapshots.")
    st.caption(f"Target: **{name}** `{sheet_id}`")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Delete Sheet", type="primary", key=f"confirm_delete_sheet_{sheet_id}"):
            _use_cases(reg).delete_sheet(sheet_id, name, actor=_actor())
            st.toast(f"Deleted {name}.", icon=":material/delete:")
            st.rerun()
    with col_cancel:
        if st.button("Cancel", key=f"cancel_delete_sheet_{sheet_id}"):
            st.rerun()


@st.dialog("Confirm Repair")
def _confirm_repair_dialog(reg: PluginRegistry, issue: IntegrityIssue) -> None:
    st.warning("Repair writes to the management database and records an audit event.")
    st.caption(f"Target: `{issue.target_id}`")
    st.caption(issue.issue)
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Run repair", type="primary", key=f"confirm_repair_{issue.repair}_{issue.target_id}"):
            _use_cases(reg).repair_integrity_issue(issue, actor=_actor())
            st.toast(f"Repaired {issue.target_id}", icon=":material/build:")
            st.rerun()
    with col_cancel:
        if st.button("Cancel", key=f"cancel_repair_{issue.repair}_{issue.target_id}"):
            st.rerun()


# ── Page: Health ─────────────────────────────────────────────────────────────


def _page_dashboard(reg: PluginRegistry) -> None:
    st.header(":material/health_and_safety: Health")

    if not _DB_PATH.exists():
        st.warning("Database has not been created yet. Start the sidecar first.")
        return

    summary = collect_dashboard_summary(_DB_PATH)
    runtime = _control_get_json("/runtime")
    diagnostics = _control_get_json("/diagnostics")
    active = diagnostics.get("active_tool") if diagnostics else _get_active_tool()
    tool_rows = collect_tool_readiness(_DB_PATH)
    sheet_issues = validate_sheet_references(_DB_PATH)
    integrity = collect_integrity_issues(_DB_PATH)

    release_issue_count = summary["readiness_issue_count"] + summary["sheet_issue_count"]
    runtime_state = "OK" if runtime and runtime.get("ok") else "Unknown"
    release_state = "OK" if release_issue_count == 0 else "Needs attention"
    integrity_state = "OK" if not integrity else "Needs repair"

    cols = st.columns(3)
    cols[0].metric("Runtime", runtime_state)
    cols[1].metric("Release readiness", release_state, delta=f"{release_issue_count} issue(s)" if release_issue_count else None)
    cols[2].metric("Data consistency", integrity_state, delta=f"{len(integrity)} issue(s)" if integrity else None)

    st.caption(
        f"Mode: {summary['mode']} · Visible tools: {summary['visible_tools']} · "
        f"Prod visible: {summary['prod_enabled_tools']} · "
        f"Active snapshots: {summary['published_modules']}/{summary['module_count']}"
    )

    st.subheader("Action Required")
    actions: list[dict[str, str]] = []
    for row in tool_rows:
        for issue in row.issues:
            actions.append({
                "Area": "Tools",
                "Target": row.tool_id,
                "Issue": issue,
            "Next step": "Open Tools, publish a snapshot or turn off Prod visibility.",
            })
    for issue in sheet_issues:
        actions.append({
            "Area": "Sheets",
            "Target": issue.sheet_id,
            "Issue": f"{issue.label} ({issue.plugin_id}): {issue.issue}",
            "Next step": "Open Sheets and fix the referenced tool before enabling Prod.",
        })
    for issue in integrity:
        actions.append({
            "Area": "Repairs",
            "Target": issue.target_id,
            "Issue": issue.issue,
            "Next step": "Open Repairs and review the proposed repair.",
        })

    if actions:
        st.dataframe(actions, use_container_width=True, hide_index=True)
    else:
        st.success("No management actions are required.")

    with st.expander("Runtime details", expanded=False):
        rcols = st.columns(4)
        rcols[0].metric("Sidecar", runtime_state)
        rcols[1].metric("Active tool", active.get("tool_id", "None") if active and active.get("active") else "None")
        rcols[2].metric("Control port", _CONTROL_PORT or "N/A")
        rcols[3].metric("Log dir", Path(runtime.get("log_dir", LOG_DIR)).name if runtime else Path(LOG_DIR).name)
        if runtime:
            st.json(runtime)
        else:
            st.caption("Runtime API is unavailable in this session.")

    with st.expander("Publish checks overview", expanded=False):
        modules = [row for row in tool_rows if row.category == "module" and row.enabled]
        preflight_rows = []
        for row in modules:
            result = module_preflight(_SCRIPTS_DIR, row.tool_id)
            preflight_rows.append({
                "tool_id": row.tool_id,
                "checks_passed": result.ok,
                "issues": "; ".join(result.issues),
            })
        if preflight_rows:
            st.dataframe(preflight_rows, use_container_width=True, hide_index=True)
        else:
            st.caption("No enabled modules found.")


def _render_integrity_repairs(reg: PluginRegistry, key_prefix: str) -> None:
    integrity = collect_integrity_issues(_DB_PATH)
    if not integrity:
        st.success("No data consistency issues found.")
        return

    manage_disabled = not _can_manage()
    for idx, issue in enumerate(integrity):
        st.markdown(f"**{issue.target_id}**")
        st.caption(issue.issue)
        if not issue.repair:
            st.info("No automatic repair is available for this issue.")
            continue
        label = {
            "disable_tool_prod": "Turn off Prod visibility for this tool",
            "disable_sheet_prod": "Turn off Prod visibility for this Sheet",
            "normalize_active_versions": "Keep newest active snapshot",
            "delete_orphan_versions": "Delete orphan version rows",
        }.get(issue.repair, "Repair")
        if st.button(
            label,
            key=f"{key_prefix}_repair_{idx}_{issue.repair}_{issue.target_id}",
            disabled=manage_disabled,
        ):
            _confirm_repair_dialog(reg, issue)
        st.divider()


def _page_repairs(reg: PluginRegistry) -> None:
    st.header(":material/build_circle: Repairs")
    st.caption("Review data consistency issues here. Health only summarizes them.")
    _render_integrity_repairs(reg, key_prefix="repairs")


# ── Page: Unified Tool Management ────────────────────────────────────────────


def _tool_header(row: dict[str, Any]) -> str:
    """Build the expander label: badge + name + tool_id + version chip + prod status."""
    badge = _category_badge(row["tool_id"])
    ver = row["active_version"]
    is_prod = bool(row["enabled_prod"])
    ver_chip = f"`v{ver}`" if ver else "`No active snapshot`"
    prod_chip = "  **PROD**" if is_prod else ""
    return f"{badge} **{row['name']}**  `{row['tool_id']}`  -  {ver_chip}{prod_chip}"


def _open_preview_modal(input_url: str, tool_name: str) -> None:
    """Fire a postMessage to the portal React to open the full-screen preview modal."""
    import streamlit.components.v1 as _components  # noqa: PLC0415
    # Sanitise values for safe JS string embedding
    safe_url = input_url.replace("\\", "").replace("'", "")
    safe_name = tool_name.replace("\\", "").replace("'", "").replace('"', "")
    _components.html(
        f"""
        <script>
        (function() {{
          window.top.postMessage({{
            source: 'cim-platform',
            type: 'OPEN_PREVIEW',
            payload: {{ url: '{safe_url}', toolName: '{safe_name}' }},
            timestamp: new Date().toISOString()
          }}, '*');
        }})();
        </script>
        """,
        height=0,
    )


def _render_module_preview(plugin_id: str, tool_id: str, manage_disabled: bool, tool_name: str = "") -> None:
    import yaml as _yaml  # noqa: PLC0415

    yaml_path = _SCRIPTS_DIR / plugin_id / "plugin.yaml"
    meta: dict[str, Any] = {}
    if yaml_path.exists():
        try:
            with open(yaml_path, encoding="utf-8") as _f:
                meta = _yaml.safe_load(_f) or {}
        except Exception:
            pass

    # Fire postMessage BEFORE the expander so it triggers even when expander is collapsed.
    trigger_key = f"_preview_trigger_{tool_id}"
    url_key = f"_preview_url_{tool_id}"
    if st.session_state.pop(trigger_key, False):
        _open_preview_modal(
            st.session_state.pop(url_key, ""),
            tool_name or tool_id,
        )

    with st.expander("Preview", expanded=False):
        desc = meta.get("description") or ""
        slug = meta.get("slug") or ""
        if desc:
            st.caption(desc)
        if slug:
            st.caption(f"Slug: `{slug}`")

        preview = _get_preview_status()
        is_this = bool(preview and preview.get("active") and preview.get("tool_id") == tool_id)
        other_running = bool(preview and preview.get("active") and not is_this)
        input_url = preview.get("input_url", "") if is_this else ""
        input_alive = preview.get("input_alive", False) if is_this else False

        if is_this and input_url and input_alive:
            st.success("Preview running in full-screen panel.", icon=":material/open_in_full:")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("↗ Reopen full-screen", key=f"reopen_preview_{tool_id}", use_container_width=True):
                    st.session_state[trigger_key] = True
                    st.session_state[url_key] = input_url
                    st.rerun()
            with col2:
                if st.button("⏹ Stop preview", key=f"stop_preview_{tool_id}", use_container_width=True):
                    _stop_preview()
                    st.rerun()
        elif other_running:
            other_id = (preview or {}).get("tool_id", "")
            st.info(f"Another preview is active (`{other_id}`). Stop it first.")
            if st.button("⏹ Stop current preview", key=f"stop_other_{tool_id}", use_container_width=True):
                _stop_preview()
                st.rerun()
        else:
            if _CONTROL_PORT and st.button(
                "▶ Start Preview",
                key=f"preview_launch_{tool_id}",
                disabled=manage_disabled,
                use_container_width=True,
            ):
                try:
                    result = _start_preview(tool_id)
                    st.session_state[trigger_key] = True
                    st.session_state[url_key] = result.get("input_url", "")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Preview failed: {exc}")
            else:
                st.caption("Opens the module's input page in a full-screen panel.")


def _get_module_to_sheets() -> dict[str, str]:
    """Return {plugin_id: 'Sheet A, Sheet B'} for modules used in sheets."""
    import sqlite3 as _sq  # noqa: PLC0415
    if not _DB_PATH.exists():
        return {}
    try:
        conn = _sq.connect(_DB_PATH)
        conn.row_factory = _sq.Row
        rows = conn.execute("""
            SELECT st.plugin_id, GROUP_CONCAT(s.name, ', ') AS sheet_names
            FROM sheet_tabs st
            JOIN sheets s ON s.sheet_id = st.sheet_id
            GROUP BY st.plugin_id
        """).fetchall()
        conn.close()
        return {row["plugin_id"]: row["sheet_names"] for row in rows}
    except Exception:
        return {}


def _prod_toggle_button(
    reg: PluginRegistry,
    tool_id: str,
    is_prod: bool,
    can_enable: bool,
    manage_disabled: bool,
    *,
    key_suffix: str = "",
) -> None:
    key = f"prod_toggle_{tool_id}{key_suffix}"
    if is_prod:
        if st.button("Prod: ON  ⏻", key=key, disabled=manage_disabled, use_container_width=True):
            _use_cases(reg).set_tool_prod_enabled(tool_id, False, actor=_actor(), source="prod_control")
            st.toast("Hidden from Prod.", icon=":material/visibility_off:")
            st.rerun()
    else:
        if st.button("Prod: OFF  ⏺", key=key, disabled=manage_disabled or not can_enable, use_container_width=True):
            _use_cases(reg).set_tool_prod_enabled(tool_id, True, actor=_actor(), source="prod_control")
            st.toast("Now visible in Prod.", icon=":material/check_circle:")
            st.rerun()


def _render_module_detail_panel(
    reg: PluginRegistry,
    selected_row: dict[str, Any],
    readiness_by_id: dict[str, Any],
    manage_disabled: bool,
) -> None:
    plugin_id = selected_row["tool_id"]
    readiness = readiness_by_id.get(plugin_id)
    is_prod = bool(selected_row["enabled_prod"])

    st.markdown(f"#### {selected_row['name']}")
    ver_text = selected_row.get("active_version") or "No snapshot"
    prod_badge = "🟢 PROD ON" if is_prod else "⚫ PROD OFF"
    checks_badge = "⚠ Needs attention" if (readiness and readiness.issues) else "✓ Checks passed"
    st.caption(f"{prod_badge}  ·  {ver_text}  ·  {checks_badge}")

    if readiness and readiness.issues:
        for issue in readiness.issues:
            st.caption(f"⚠ {issue}")

    preflight = module_preflight(_SCRIPTS_DIR, plugin_id)
    snapshot_diff = module_snapshot_diff(_SCRIPTS_DIR, _DB_PATH, plugin_id)

    if preflight.ok:
        if snapshot_diff.has_active_snapshot:
            change_count = len(snapshot_diff.added) + len(snapshot_diff.changed) + len(snapshot_diff.removed)
            st.caption(f"{change_count} file(s) changed since last snapshot." if change_count else "No file changes since last snapshot.")
        else:
            st.caption(f"No snapshot yet — {snapshot_diff.current_file_count} file(s) ready to publish.")
    else:
        st.error("Publish checks failed.")
        for issue in preflight.issues:
            st.caption(f"- {issue}")

    pub_col1, pub_col2 = st.columns(2)
    with pub_col1:
        if st.button(
            "Publish snapshot",
            key=f"publish_{plugin_id}",
            type="primary",
            disabled=manage_disabled or not preflight.ok,
            use_container_width=True,
        ):
            _create_snapshot_dialog(reg, plugin_id, plugin_id)
    with pub_col2:
        if st.button(
            "Publish & go live",
            key=f"pub_live_{plugin_id}",
            disabled=manage_disabled or not preflight.ok,
            use_container_width=True,
        ):
            _publish_dialog(reg, plugin_id, plugin_id)

    st.divider()

    can_enable_prod = bool(
        readiness and readiness.prod_ready and readiness.has_active_version
    )
    prod_col, hint_col = st.columns([1, 2])
    with prod_col:
        _prod_toggle_button(reg, plugin_id, is_prod, can_enable_prod, manage_disabled)
    with hint_col:
        if not can_enable_prod and not is_prod:
            st.caption("Need a valid snapshot & passing checks first.")

    _render_module_preview(plugin_id, plugin_id, manage_disabled, tool_name=selected_row.get("name", plugin_id))

    try:
        versions = reg.list_versions(plugin_id)
    except Exception:
        versions = []
    with st.expander("Version history", expanded=False):
        if not versions:
            st.caption("No snapshots yet.")
        for ver in versions:
            active_badge = "  **active**" if ver.is_active else ""
            st.markdown(
                f"`v{ver.version}` #{ver.version_id}{active_badge}"
                f" — {ver.created_at[:16]}"
                + (f" — {ver.changelog}" if ver.changelog else "")
            )
            if not ver.is_active and st.button(
                f"Rollback to #{ver.version_id}",
                key=f"rollback_{plugin_id}_{ver.version_id}",
                disabled=manage_disabled,
            ):
                _confirm_rollback_dialog(reg, plugin_id, ver.version_id)

    with st.expander("⚠ Danger zone", expanded=False):
        st.caption("Archive hides without deleting snapshots. Delete draft only works on unpublished tools.")
        danger_cols = st.columns(2)
        with danger_cols[0]:
            if st.button("Archive", key=f"archive_{plugin_id}", disabled=manage_disabled, use_container_width=True):
                _confirm_archive_dialog(reg, plugin_id, selected_row["name"])
        with danger_cols[1]:
            if st.button(
                "Delete draft",
                key=f"delete_draft_{plugin_id}",
                disabled=manage_disabled or bool(selected_row["active_version"]) or bool(selected_row["enabled_prod"]),
                use_container_width=True,
            ):
                _confirm_delete_draft_tool_dialog(reg, plugin_id, selected_row["name"])


def _render_modules_tab(
    reg: PluginRegistry,
    module_rows: list[dict[str, Any]],
    readiness_by_id: dict[str, Any],
    module_to_sheets: dict[str, str],
    manage_disabled: bool,
) -> None:
    _render_module_import_and_scaffold(reg, manage_disabled)

    if not module_rows:
        st.info("No modules registered yet. Use Upload / New Module above.")
        return

    search_col, filter_col = st.columns([2, 1])
    with search_col:
        search = st.text_input("Search", placeholder="Name or ID", label_visibility="collapsed", key="module_search")
    with filter_col:
        status_filter = st.selectbox(
            "Status",
            ["All", "Prod: ON", "Needs attention", "No snapshot"],
            key="module_status_filter",
            label_visibility="collapsed",
        )

    filtered = module_rows
    if search.strip():
        q = search.strip().lower()
        filtered = [r for r in filtered if q in r["name"].lower() or q in r["tool_id"].lower()]
    if status_filter == "Prod: ON":
        filtered = [r for r in filtered if r["enabled_prod"]]
    elif status_filter == "Needs attention":
        filtered = [r for r in filtered if readiness_by_id.get(r["tool_id"]) and readiness_by_id[r["tool_id"]].issues]
    elif status_filter == "No snapshot":
        filtered = [r for r in filtered if not r.get("active_version")]

    if not filtered:
        st.info("No modules match the filter.")
        return

    detail_options = [r["tool_id"] for r in filtered]
    if st.session_state.get("module_selected") not in detail_options:
        st.session_state["module_selected"] = detail_options[0]
        # Filter changed and pushed the selection out — reset table checkbox too
        st.session_state["modules_table"] = {"selection": {"rows": [0], "columns": []}}

    sel_id = st.session_state["module_selected"]
    sel_idx = next((i for i, r in enumerate(filtered) if r["tool_id"] == sel_id), 0)
    # Only initialise on first load. Do NOT overwrite on every rerun — that would
    # clobber the click Streamlit already stored in the session state, causing the
    # selection to snap back to row 0 after each click.
    if "modules_table" not in st.session_state:
        st.session_state["modules_table"] = {"selection": {"rows": [sel_idx], "columns": []}}

    left_col, right_col = st.columns([0.55, 0.45])

    with left_col:
        table_data = [
            {
                "Name": row["name"],
                "ID": row["tool_id"],
                "Prod": "ON" if row["enabled_prod"] else "off",
                "Version": row.get("active_version") or "—",
                "Used in": module_to_sheets.get(row["tool_id"], "—"),
                "_id": row["tool_id"],
            }
            for row in filtered
        ]
        df = pd.DataFrame([{k: v for k, v in r.items() if k != "_id"} for r in table_data])
        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="modules_table",
            column_config={
                "Name": st.column_config.TextColumn("Name"),
                "ID": st.column_config.TextColumn("ID", width="small"),
                "Prod": st.column_config.TextColumn("Prod", width="small"),
                "Version": st.column_config.TextColumn("Version", width="small"),
                "Used in": st.column_config.TextColumn("Used in"),
            },
        )
        # Update selection — no extra st.rerun(); on_select already triggered one
        if event.selection.rows:
            st.session_state["module_selected"] = table_data[event.selection.rows[0]]["_id"]

    with right_col:
        sel_id = st.session_state["module_selected"]
        sel_row = next((r for r in module_rows if r["tool_id"] == sel_id), None)
        if sel_row:
            _render_module_detail_panel(reg, sel_row, readiness_by_id, manage_disabled)


def _render_sheets_tab(
    reg: PluginRegistry,
    sheet_rows: list[dict[str, Any]],
    readiness_by_id: dict[str, Any],
    manage_disabled: bool,
) -> None:
    if not sheet_rows:
        st.info("No sheets registered. Create one in the Sheets page.")
        return

    detail_options = [r["tool_id"] for r in sheet_rows]
    if st.session_state.get("tools_sheet_selected") not in detail_options:
        st.session_state["tools_sheet_selected"] = detail_options[0]

    left_col, right_col = st.columns([0.5, 0.5])

    with left_col:
        table_data = []
        for row in sheet_rows:
            sheet_id = row["tool_id"][len("sheet-"):]
            issues = validate_sheet_prod_readiness(_DB_PATH, sheet_id)
            table_data.append({
                "Name": row["name"],
                "Prod": "ON" if row["enabled_prod"] else "off",
                "Checks": "⚠" if issues else "✓",
                "_id": row["tool_id"],
            })
        df = pd.DataFrame([{k: v for k, v in r.items() if k != "_id"} for r in table_data])
        event = st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="sheets_tools_table",
            column_config={
                "Name": st.column_config.TextColumn("Name"),
                "Prod": st.column_config.TextColumn("Prod", width="small"),
                "Checks": st.column_config.TextColumn("Checks", width="small"),
            },
        )
        if event.selection.rows:
            picked = table_data[event.selection.rows[0]]["_id"]
            if picked != st.session_state.get("tools_sheet_selected"):
                st.session_state["tools_sheet_selected"] = picked
                st.rerun()

    with right_col:
        sel_id = st.session_state["tools_sheet_selected"]
        sel_row = next((r for r in sheet_rows if r["tool_id"] == sel_id), None)
        if sel_row:
            sheet_id = sel_id[len("sheet-"):]
            st.markdown(f"#### {sel_row['name']}")
            is_prod = bool(sel_row["enabled_prod"])
            issues = validate_sheet_prod_readiness(_DB_PATH, sheet_id)
            if issues:
                st.warning("Readiness issues — resolve before enabling Prod.")
                for issue in issues:
                    st.caption(f"⚠ {issue.label} ({issue.plugin_id}): {issue.issue}")
            else:
                st.success("All checks passed.", icon=":material/check_circle:")
            prod_col, _ = st.columns([1, 1])
            with prod_col:
                _prod_toggle_button(reg, sel_id, is_prod, not bool(issues), manage_disabled, key_suffix="_sheet")
            with st.expander("⚠ Danger zone", expanded=False):
                if st.button("Archive sheet", key=f"archive_sheet_{sel_id}", disabled=manage_disabled, use_container_width=True):
                    _confirm_archive_dialog(reg, sel_id, sel_row["name"])


def _render_external_tab(
    reg: PluginRegistry,
    external_rows: list[dict[str, Any]],
    readiness_by_id: dict[str, Any],
    manage_disabled: bool,
) -> None:
    if not external_rows:
        st.info("No external tools registered.")
        return
    for row in external_rows:
        tool_id = row["tool_id"]
        is_prod = bool(row["enabled_prod"])
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.markdown(f"**{row['name']}**  `{tool_id}`")
            st.caption("Opens as a native window (not an iframe).")
        with c2:
            st.caption("PROD ON" if is_prod else "PROD OFF")
        with c3:
            if _CONTROL_PORT and st.button("Launch", key=f"ext_launch_{tool_id}", use_container_width=True):
                try:
                    _start_tool(tool_id)
                    st.toast("External tool launched.", icon=":material/rocket_launch:")
                except Exception as exc:
                    st.error(f"Launch failed: {exc}")
        st.divider()


def _page_tools(reg: PluginRegistry) -> None:
    st.header(":material/extension: Tools")
    manage_disabled = not _can_manage()

    if not _DB_PATH.exists():
        st.warning("Database has not been created yet. Start the sidecar first.")
        return

    try:
        rows = _load_tool_rows()
        archived = _load_archived_rows()
    except Exception as exc:
        st.error(f"Could not load tools: {exc}")
        return

    readiness_by_id = {item.tool_id: item for item in collect_tool_readiness(_DB_PATH)}
    module_to_sheets = _get_module_to_sheets()

    module_rows = [
        r for r in rows
        if readiness_by_id.get(r["tool_id"]) and readiness_by_id[r["tool_id"]].category == "module"
    ]
    sheet_rows = [r for r in rows if r["tool_id"].startswith("sheet-")]
    external_rows = [
        r for r in rows
        if readiness_by_id.get(r["tool_id"]) and readiness_by_id[r["tool_id"]].category == "external"
    ]

    active = _get_active_tool()
    if active and active.get("active"):
        st.info(f"Running: `{active['tool_id']}`", icon=":material/play_circle:")

    tab_modules, tab_sheets, tab_external = st.tabs([
        f"Modules ({len(module_rows)})",
        f"Sheets ({len(sheet_rows)})",
        f"External ({len(external_rows)})",
    ])

    with tab_modules:
        _render_modules_tab(reg, module_rows, readiness_by_id, module_to_sheets, manage_disabled)

    with tab_sheets:
        _render_sheets_tab(reg, sheet_rows, readiness_by_id, manage_disabled)

    with tab_external:
        _render_external_tab(reg, external_rows, readiness_by_id, manage_disabled)

    _render_inactive_tools(reg, archived, manage_disabled)



def _render_module_import_and_scaffold(reg: PluginRegistry, manage_disabled: bool) -> None:
    with st.expander("Upload / New Module", expanded=False):
        import_tab, scaffold_tab = st.tabs(["Upload Module Zip", "New Module"])
        with import_tab:
            upload = st.file_uploader("Module package zip", type=["zip"], key="module_package_zip")
            allow_update = st.checkbox("Update existing module when IDs match", key="module_import_allow_update")
            default_author = st.session_state.get("publish_author", os.environ.get("USERNAME") or "admin")
            author = st.text_input("Import author", value=default_author, key="module_import_author")
            changelog = st.text_area(
                "Import changelog",
                placeholder="Describe the imported module or update.",
                height=80,
                key="module_import_changelog",
            )
            if upload is not None:
                package_bytes = upload.getvalue()
                try:
                    report = _use_cases(reg).analyze_module_package(package_bytes, upload.name)
                    _render_package_report(report.public_dict())
                    can_import = report["ok"] if isinstance(report, dict) else report.ok
                    if st.button(
                        "Upload as new module snapshot",
                        type="primary",
                        disabled=manage_disabled or not can_import or not changelog.strip() or not author.strip(),
                        key="module_import_confirm",
                    ):
                        result = _use_cases(reg).import_module_package(
                            package_bytes,
                            upload.name,
                            changelog=changelog.strip(),
                            author=author.strip(),
                            actor=_actor(),
                            allow_update=allow_update,
                        )
                        st.session_state["publish_author"] = author.strip()
                        st.toast(
                            f"Imported {result.report.plugin_id} snapshot #{result.version_id}. Prod visibility is off.",
                            icon=":material/check_circle:",
                        )
                        st.info("Next step: select the module below, review checks, then enable Prod visibility when ready.")
                        st.rerun()
                except ModulePackageError as exc:
                    _render_package_report(exc.report.public_dict())
                except Exception as exc:
                    st.error(f"Import failed: {exc}")
            else:
                st.caption("Upload a zip package to validate it before import.")

        with scaffold_tab:
            name = st.text_input("Module name", key="scaffold_name")
            description = st.text_area("Description", height=80, key="scaffold_description")
            requested_id = st.text_input("Module ID", placeholder="Leave blank for next module_NNN", key="scaffold_plugin_id")
            scaffold_author = st.text_input("Author", value=os.environ.get("USERNAME") or "admin", key="scaffold_author")
            if st.button(
                "Create module scaffold",
                type="primary",
                disabled=manage_disabled or not name.strip() or not scaffold_author.strip(),
                key="scaffold_create",
            ):
                try:
                    result = _use_cases(reg).create_module_scaffold(
                        name=name.strip(),
                        description=description.strip(),
                        author=scaffold_author.strip(),
                        actor=_actor(),
                        plugin_id=requested_id.strip() or None,
                    )
                    st.toast(f"Created {result.plugin_id}.", icon=":material/add_circle:")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Create module failed: {exc}")


def _render_package_report(report: dict[str, Any]) -> None:
    status = "Ready to import" if report.get("ok") else "Blocked"
    st.caption(
        f"{status} | `{report.get('plugin_id') or 'unknown'}` "
        f"v{report.get('version') or '?'} | files: {report.get('file_count', 0)}"
    )
    if report.get("package_hash"):
        st.caption(f"SHA-256: `{report['package_hash'][:16]}...`")
    if report.get("issues"):
        st.error("Package validation found issues.")
        for issue in report["issues"]:
            st.markdown(f"**{issue['code']}**: {issue['message']}")
            if issue.get("file"):
                st.caption(f"File: `{issue['file']}`")
            if issue.get("how_to_fix"):
                st.caption(f"Fix: {issue['how_to_fix']}")
    else:
        st.success("Package validation passed.")
    with st.expander("Package files and diff", expanded=False):
        st.json({
            "files": report.get("files", []),
            "added": report.get("added", []),
            "changed": report.get("changed", []),
            "removed": report.get("removed", []),
            "is_update": report.get("is_update", False),
        })


def _render_inactive_tools(reg: PluginRegistry, archived: list[dict[str, Any]], manage_disabled: bool) -> None:
    st.divider()
    st.subheader("Inactive Tools")
    st.caption("Inactive tools are hidden from the main list and Portal until restored.")
    if not archived:
        st.info("No inactive tools.")
        return
    inactive_rows = [
        {
            "tool_id": row["tool_id"],
            "name": row["name"],
            "active_snapshot": row["active_version"] or "",
            "prod_visibility": "On" if row["enabled_prod"] else "Off",
        }
        for row in archived
    ]
    st.dataframe(pd.DataFrame(inactive_rows), use_container_width=True, hide_index=True)
    restore_id = st.selectbox(
        "Restore inactive tool",
        options=[row["tool_id"] for row in archived],
        format_func=lambda tool_id: next(
            f"{row['name']} ({row['tool_id']})" for row in archived if row["tool_id"] == tool_id
        ),
        key="inactive_restore_target",
    )
    restore_row = next(row for row in archived if row["tool_id"] == restore_id)
    if st.button("Restore selected inactive tool", key=f"restore_{restore_id}", disabled=manage_disabled):
        _confirm_restore_dialog(reg, restore_id, restore_row["name"])


# ── Sheet tab editor ──────────────────────────────────────────────────────────



def _sheet_step_public(step: dict[str, Any]) -> dict[str, str]:
    return {"plugin_id": str(step.get("plugin_id", "")), "label": str(step.get("label", ""))}


def _sheet_public_steps(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [_sheet_step_public(step) for step in steps]


def _sheet_draft_id(key: str, index: int) -> str:
    counter_key = f"{key}_draft_counter"
    st.session_state[counter_key] = int(st.session_state.get(counter_key, 0)) + 1
    return f"{key}_{index}_{st.session_state[counter_key]}"


def _prepare_sheet_draft_steps(key: str, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for i, step in enumerate(steps):
        item = dict(step)
        item.setdefault("_draft_id", _sheet_draft_id(key, i))
        prepared.append(item)
    return prepared


def _sheet_draft_is_dirty(
    name: str,
    description: str,
    steps: list[dict[str, Any]],
    sheet: Any,
    initial_tabs: list[dict[str, str]],
) -> bool:
    saved_description = sheet.description or ""
    return (
        name != sheet.name
        or description != saved_description
        or _sheet_public_steps(steps) != initial_tabs
    )


def _sheet_issue_message(issue_texts: list[str]) -> tuple[str, str]:
    issue_set = set(issue_texts)
    if "Referenced plugin does not exist in tools." in issue_set:
        return "Missing", "Remove this step or register the referenced plugin."
    if "Referenced plugin is archived." in issue_set:
        return "Archived", "Restore the referenced tool before using this Sheet in Prod."
    has_snapshot_issue = "Prod sheet references a module without an active snapshot." in issue_set
    has_prod_issue = "Prod sheet references a plugin not enabled in Prod." in issue_set
    if has_snapshot_issue and has_prod_issue:
        return "Needs release", "Publish an active snapshot, then enable Prod visibility."
    if has_snapshot_issue:
        return "Needs snapshot", "Publish an active snapshot for this module."
    if has_prod_issue:
        return "Enable Prod", "Enable Prod visibility for this referenced tool."
    return "Blocked", "; ".join(issue_texts)


def _sheet_readiness_summary(issues: list[Any]) -> tuple[str, dict[tuple[str, str], dict[str, str]], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for issue in issues:
        grouped.setdefault((issue.plugin_id, issue.label), []).append(issue.issue)

    readiness_by_step: dict[tuple[str, str], dict[str, str]] = {}
    detail_rows: list[dict[str, str]] = []
    for (plugin_id, label), issue_texts in grouped.items():
        status, action = _sheet_issue_message(issue_texts)
        readiness_by_step[(plugin_id, label)] = {"status": status, "action": action}
        detail_rows.append({"step": label or "Sheet", "module": plugin_id or "-", "status": status, "action": action})

    if not detail_rows:
        return "Prod ready", readiness_by_step, detail_rows

    status_counts: dict[str, int] = {}
    for row in detail_rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    pieces = [f"{count} {status.lower()}" for status, count in sorted(status_counts.items())]
    return f"Prod blocked: {len(detail_rows)} step(s) need attention ({', '.join(pieces)}).", readiness_by_step, detail_rows


def _sheet_steps_editor(
    key: str,
    plugins: list,
    initial_tabs: list[dict] | None = None,
    readiness_by_step: dict[tuple[str, str], dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    if key not in st.session_state:
        st.session_state[key] = _prepare_sheet_draft_steps(key, list(initial_tabs or []))

    steps: list[dict[str, Any]] = st.session_state[key]
    plugin_ids = [p.plugin_id for p in plugins]
    plugin_names = {p.plugin_id: p.name for p in plugins}
    readiness_by_step = readiness_by_step or {}
    show_readiness = bool(readiness_by_step)

    if not plugin_ids:
        st.warning("No modules are available to add to this Sheet.")
        return _sheet_public_steps(steps)

    col_ratios = [0.5, 2.5, 3.2, 1.2, 1.8] if show_readiness else [0.5, 2.5, 3.2, 1.8]
    header_labels = ["#", "Label", "Module", "Readiness", "Actions"] if show_readiness else ["#", "Label", "Module", "Actions"]

    st.markdown("**Steps**")
    header = st.columns(col_ratios)
    for col, label in zip(header, header_labels):
        col.markdown(f"**{label}**")

    remove_idx: int | None = None
    move: tuple[int, int] | None = None
    for i, step in enumerate(steps):
        draft_id = step.setdefault("_draft_id", _sheet_draft_id(key, i))
        cols = st.columns(col_ratios)
        with cols[0]:
            st.markdown(str(i + 1))
        with cols[1]:
            steps[i]["label"] = st.text_input(
                "Label",
                value=step.get("label", ""),
                key=f"{key}_label_{draft_id}",
                label_visibility="collapsed",
            )
        with cols[2]:
            current = step.get("plugin_id", plugin_ids[0])
            idx = plugin_ids.index(current) if current in plugin_ids else 0
            steps[i]["plugin_id"] = st.selectbox(
                "Module",
                options=plugin_ids,
                format_func=lambda plugin_id: f"{plugin_names.get(plugin_id, plugin_id)} ({plugin_id})",
                index=idx,
                key=f"{key}_plugin_{draft_id}",
                label_visibility="collapsed",
            )
        action_col_idx = 3
        if show_readiness:
            with cols[3]:
                status = readiness_by_step.get(
                    (steps[i].get("plugin_id", ""), steps[i].get("label", "")),
                    {"status": "Ready"},
                )["status"]
                st.caption(status)
            action_col_idx = 4
        with cols[action_col_idx]:
            a, b, c = st.columns(3)
            if a.button("Up", key=f"{key}_up_{draft_id}", disabled=i == 0):
                move = (i, i - 1)
            if b.button("Down", key=f"{key}_down_{draft_id}", disabled=i == len(steps) - 1):
                move = (i, i + 1)
            if c.button("Del", key=f"{key}_del_{draft_id}"):
                remove_idx = i

    if move is not None:
        src, dst = move
        steps[src], steps[dst] = steps[dst], steps[src]
        st.rerun()
    if remove_idx is not None:
        steps.pop(remove_idx)
        st.rerun()

    if st.button("＋ Add step", key=f"{key}_add_step"):
        default_plugin = plugin_ids[0]
        steps.append({
            "_draft_id": _sheet_draft_id(key, len(steps)),
            "plugin_id": default_plugin,
            "label": plugin_names.get(default_plugin, default_plugin),
        })
        st.rerun()

    return _sheet_public_steps(steps)


def _page_sheets(reg: PluginRegistry) -> None:
    st.header(":material/dashboard: Sheets")
    manage_disabled = not _can_manage()
    plugins = reg.list_plugins()

    # ── 上半部：新增 Sheet ────────────────────────────────────────
    with st.expander("＋ New Sheet", expanded=st.session_state.get("expand_new_sheet", False)):
        nc = st.columns([2, 3, 1])
        with nc[0]:
            new_name = st.text_input("Sheet name", key="new_sheet_name_v2", placeholder="e.g. Defect Inspection", label_visibility="collapsed")
        with nc[1]:
            new_desc = st.text_input("Description", key="new_sheet_desc_v2", placeholder="Description (optional)", label_visibility="collapsed")
        with nc[2]:
            if st.button("Create", type="primary", key="save_new_sheet_v2",
                         disabled=manage_disabled or not new_name.strip(),
                         use_container_width=True):
                sheet_id = new_name.strip().lower().replace(" ", "_")
                try:
                    _use_cases(reg).create_or_update_sheet(
                        sheet_id, new_name.strip(), new_desc.strip(), [],
                        actor=_actor(), action="create",
                    )
                    st.toast(f"Created Sheet '{new_name.strip()}'.", icon=":material/check_circle:")
                    st.session_state["expand_new_sheet"] = False
                    st.rerun()
                except Exception as exc:
                    st.error(f"Create Sheet failed: {exc}")

    # ── 上半部：Sheet 列表 ────────────────────────────────────────
    sheets = reg.list_sheets()
    if not sheets:
        st.info("No Sheets yet. Create one above.")
        return

    df = pd.DataFrame([{
        "Name": s.name,
        "Dev": "On" if s.enabled_dev else "Off",
        "Prod": "On" if s.enabled_prod else "Off",
        "Steps": len(s.tabs),
        "_id": s.sheet_id,
    } for s in sheets])

    evt = st.dataframe(
        df[["Name", "Dev", "Prod", "Steps"]],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="sheets_table",
    )

    sel_rows = evt.selection.rows
    if not sel_rows:
        st.caption("選擇上方的 Sheet 來編輯其 Steps。")
        return

    sheet = next(s for s in sheets if s.sheet_id == df.iloc[sel_rows[0]]["_id"])
    prod_issues = validate_sheet_prod_readiness(_DB_PATH, sheet.sheet_id)
    summary, readiness_by_step, _ = _sheet_readiness_summary(prod_issues)

    st.divider()

    # ── 下半部：Sheet 操作列 ──────────────────────────────────────
    rename_key = f"renaming_{sheet.sheet_id}"
    if st.session_state.get(rename_key):
        rc = st.columns([2, 3, 1, 1])
        with rc[0]:
            edit_name = st.text_input("Name", value=sheet.name,
                                      key=f"rename_name_{sheet.sheet_id}",
                                      label_visibility="collapsed")
        with rc[1]:
            edit_desc = st.text_input("Description", value=sheet.description,
                                      key=f"rename_desc_{sheet.sheet_id}",
                                      label_visibility="collapsed",
                                      placeholder="Description (optional)")
        with rc[2]:
            if st.button("Save", type="primary", key=f"rename_save_{sheet.sheet_id}", use_container_width=True):
                if not edit_name.strip():
                    st.error("Name is required.")
                else:
                    try:
                        draft_key = f"sheet_steps_{sheet.sheet_id}"
                        current_steps = _sheet_public_steps(
                            st.session_state.get(draft_key,
                                _prepare_sheet_draft_steps(draft_key,
                                    [{"plugin_id": t.plugin_id, "label": t.label} for t in sheet.tabs]))
                        )
                        _use_cases(reg).create_or_update_sheet(
                            sheet.sheet_id, edit_name.strip(), edit_desc.strip(),
                            current_steps, actor=_actor(), action="update",
                        )
                        st.session_state.pop(rename_key, None)
                        st.toast("Saved.", icon=":material/check_circle:")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        with rc[3]:
            if st.button("Cancel", key=f"rename_cancel_{sheet.sheet_id}", use_container_width=True):
                st.session_state.pop(rename_key, None)
                st.rerun()
    else:
        st.subheader(sheet.name)
        if sheet.description:
            st.caption(sheet.description)

        ac = st.columns([1, 1, 1, 1, 4])
        with ac[0]:
            if st.button("Rename", key=f"rename_btn_{sheet.sheet_id}",
                         disabled=manage_disabled, use_container_width=True):
                st.session_state[rename_key] = True
                st.rerun()
        with ac[1]:
            dev_label = "Dev: On" if sheet.enabled_dev else "Dev: Off"
            if st.button(dev_label, key=f"dev_btn_{sheet.sheet_id}",
                         disabled=manage_disabled, use_container_width=True):
                _use_cases(reg).set_sheet_dev_enabled(sheet.sheet_id, not sheet.enabled_dev, actor=_actor())
                st.rerun()
        with ac[2]:
            prod_label = "Prod: On" if sheet.enabled_prod else "Prod: Off"
            if st.button(prod_label, key=f"prod_btn_{sheet.sheet_id}",
                         disabled=manage_disabled or (not sheet.enabled_prod and bool(prod_issues)),
                         use_container_width=True):
                try:
                    _use_cases(reg).set_sheet_prod_enabled(sheet.sheet_id, not sheet.enabled_prod, actor=_actor())
                    st.rerun()
                except SheetProdReadinessError as exc:
                    failed_summary, _, failed_details = _sheet_readiness_summary(exc.issues)
                    st.error(failed_summary)
                    if failed_details:
                        st.dataframe(pd.DataFrame(failed_details), use_container_width=True, hide_index=True)
        with ac[3]:
            if st.button("Delete", key=f"delete_btn_{sheet.sheet_id}",
                         disabled=manage_disabled, use_container_width=True):
                _confirm_delete_sheet_dialog(reg, sheet.sheet_id, sheet.name)

        if prod_issues:
            st.warning(summary)

    # ── 下半部：Steps 編輯 ────────────────────────────────────────
    draft_key = f"sheet_steps_{sheet.sheet_id}"
    initial_tabs = [{"plugin_id": tab.plugin_id, "label": tab.label} for tab in sheet.tabs]
    steps = _sheet_steps_editor(draft_key, plugins,
                                initial_tabs=initial_tabs,
                                readiness_by_step=readiness_by_step)

    draft_steps = st.session_state.get(draft_key, [])
    steps_dirty = _sheet_public_steps(draft_steps) != initial_tabs

    sc = st.columns([1, 1, 5])
    with sc[0]:
        if st.button("Save Steps", type="primary", key=f"sheet_save_{sheet.sheet_id}",
                     disabled=manage_disabled or not steps_dirty, use_container_width=True):
            if not steps:
                st.error("Add at least one step before saving.")
            else:
                try:
                    _use_cases(reg).create_or_update_sheet(
                        sheet.sheet_id, sheet.name, sheet.description, steps,
                        actor=_actor(), action="update",
                    )
                    st.toast("Steps saved.", icon=":material/check_circle:")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Save failed: {exc}")
    with sc[1]:
        if st.button("Discard", key=f"sheet_discard_{sheet.sheet_id}", use_container_width=True):
            st.session_state[draft_key] = _prepare_sheet_draft_steps(draft_key, initial_tabs)
            st.rerun()



def _fmt_ms(ms: float | None) -> str:
    if ms is None:
        return "—"
    s = int(ms) // 1000
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"


def _page_runs(reg: PluginRegistry) -> None:
    st.header(":material/monitoring: Runs & Usage")
    store = _store()

    # 工具名稱對照表
    tool_names = {p.plugin_id: p.name for p in reg.list_plugins()}

    # ── 時間範圍選擇 ──────────────────────────────────────────────
    days_map = {"7 天": 7, "30 天": 30, "90 天": 90}
    period = st.radio("時間範圍", list(days_map.keys()), index=1,
                      horizontal=True, label_visibility="collapsed")
    days = days_map[period]

    usage_rows = store.usage_summary(days=days)
    if not usage_rows:
        st.info("目前沒有執行記錄。請從 Portal 或 Tools 頁面啟動工具。")
        return

    # ── KPI 總覽 ─────────────────────────────────────────────────
    total_runs = sum(r["run_count"] for r in usage_rows)
    total_failed = sum(r["failed_count"] for r in usage_rows)
    total_completed = sum(r["completed_count"] for r in usage_rows)
    success_rate = f"{total_completed / total_runs * 100:.0f}%" if total_runs else "—"
    active_tools = len(usage_rows)

    kc = st.columns(4)
    kc[0].metric("總執行次數", total_runs)
    kc[1].metric("成功率", success_rate)
    kc[2].metric("失敗次數", total_failed)
    kc[3].metric("活躍工具", active_tools)

    st.divider()

    # ── 工具使用排行 ──────────────────────────────────────────────
    summary_data = []
    for r in usage_rows:
        tid = r["tool_id"]
        runs = r["run_count"]
        failed = r["failed_count"]
        rate = (r["completed_count"] / runs * 100) if runs else 0
        rate_str = f"{rate:.0f}% ⚠" if rate < 80 and runs >= 3 else f"{rate:.0f}%"
        summary_data.append({
            "工具名稱": tool_names.get(tid, tid),
            "執行次數": runs,
            "成功率": rate_str,
            "最後執行": r.get("last_started_at", "—"),
            "_tool_id": tid,
        })

    df_summary = pd.DataFrame(summary_data)

    evt = st.dataframe(
        df_summary[["工具名稱", "執行次數", "成功率", "最後執行"]],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="runs_table",
    )

    # ── 選中工具的執行記錄 ────────────────────────────────────────
    sel_rows = evt.selection.rows
    if not sel_rows:
        st.caption("點選上方工具列查看執行記錄。")
        return

    selected_tool_id = df_summary.iloc[sel_rows[0]]["_tool_id"]
    selected_tool_name = tool_names.get(selected_tool_id, selected_tool_id)

    st.divider()
    st.subheader(f"{selected_tool_name} 執行記錄")

    runs = store.list_tool_run_rows(limit=50, tool_id=selected_tool_id)
    if not runs:
        st.caption("尚無執行記錄。")
        return

    run_data = []
    for r in runs:
        row = {
            "時間": r.get("started_at", "—"),
            "狀態": r.get("status", "—"),
            "時長": _fmt_ms(r.get("duration_ms")),
            "執行者": r.get("actor", "—"),
        }
        if r.get("status") == "failed" and r.get("error_summary"):
            row["錯誤"] = r["error_summary"]
        else:
            row["錯誤"] = "—"
        run_data.append(row)

    st.dataframe(pd.DataFrame(run_data), use_container_width=True, hide_index=True)


def _page_permissions(reg: PluginRegistry) -> None:
    st.header(":material/lock: Permissions")
    st.info(
        "This page is read-only for now. Local role checks use `admin` by default; "
        "enterprise permission editing will be wired to a production identity service later."
    )

    st.markdown("**Defined roles:**")
    roles = _store().list_role_rows()
    for r in roles:
        st.markdown(f"- **{r['role_id']}** ({r['name']}): {r['description'] or '-'}")

    st.markdown("---")
    st.markdown("**Current plugin permission matrix:**")

    plugins = reg.list_plugins()
    if not plugins:
        st.info("No plugins are registered yet.")
        return

    perms = _store().list_permission_rows()

    if not perms:
        st.caption("No custom permission rows yet. Roles default to full local access.")
    else:
        table = {
            "Plugin": [r["plugin_id"] for r in perms],
            "Role": [r["role_id"] for r in perms],
            "Can view": ["yes" if r["can_view"] else "no" for r in perms],
            "Can execute": ["yes" if r["can_execute"] else "no" for r in perms],
        }
        st.dataframe(table, use_container_width=True)


# ── Page: Audit / Backup ─────────────────────────────────────────────────────


def _page_system(reg: PluginRegistry) -> None:
    import datetime
    import json as _json

    st.header(":material/history: Audit & Database")
    backend = _management_backend()

    backend_cols = st.columns(3)
    backend_cols[0].metric("Backend", backend.upper())
    backend_cols[1].metric("Backup policy", "Local JSON" if backend == "sqlite" else "External DBA")
    backend_cols[2].metric("Audit", "Enabled")

    st.subheader("Recent Audit Events")
    try:
        events = reg.list_audit_events(limit=50)
    except Exception:
        events = []
    if events:
        st.dataframe(
            [
                {
                    "event_id": e.event_id,
                    "created_at": e.created_at,
                    "actor": e.actor,
                    "action": e.action,
                    "target_type": e.target_type,
                    "target_id": e.target_id,
                    "details": e.details,
                }
                for e in events
            ],
            use_container_width=True,
        )
    else:
        st.caption("No audit events yet.")

    st.divider()
    st.subheader("Database")

    if backend != "sqlite":
        st.info(
            "Oracle production backups are managed outside Management Center by the database backup policy "
            "(for example RMAN, storage snapshots, retention rules, and DBA restore procedures). "
            "This page keeps audit visibility but does not export or restore Oracle data."
        )
        dsn_status = "Configured" if (os.environ.get("CIM_ORACLE_DSN") or os.environ.get("ORACLE_DSN")) else "Not shown"
        st.dataframe(
            pd.DataFrame(
                [
                    {"item": "Backend", "value": backend.upper()},
                    {"item": "Oracle DSN", "value": dsn_status},
                    {"item": "Backup execution", "value": "External DBA / Oracle policy"},
                    {"item": "JSON restore", "value": "Disabled for non-SQLite backends"},
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        return

    st.subheader("Local SQLite Backup")

    if not _DB_PATH.exists():
        st.warning("Database has not been created yet. Start the sidecar first.")
        return

    try:
        dump = _store().dump_all_tables()
    except Exception as exc:
        st.error(f"Could not read database: {exc}")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = _json.dumps(dump, ensure_ascii=False, indent=2, default=str)

    st.download_button(
        label="Download local SQLite backup (JSON)",
        data=payload,
        file_name=f"cim_db_backup_{ts}.json",
        mime="application/json",
        use_container_width=True,
    )
    st.caption("This local backup covers the SQLite management database only. It does not include image datasets, model files, or external assets.")

    with st.expander("Restore dry-run", expanded=False):
        backup_upload = st.file_uploader("Backup JSON", type=["json"], key="backup_restore_dry_run")
        if backup_upload is None:
            st.caption("Upload a backup JSON to validate table names and row counts before any restore workflow.")
        else:
            try:
                backup_data = json.loads(backup_upload.getvalue().decode("utf-8"))
                if not isinstance(backup_data, dict):
                    st.error("Backup JSON must be an object keyed by table name.")
                else:
                    current_tables = set(dump)
                    backup_tables = set(backup_data)
                    st.success("Backup JSON is readable. This is a dry-run only; no data was changed.")
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "table": table,
                                    "current_rows": len(dump.get(table, [])),
                                    "backup_rows": len(backup_data.get(table, [])) if isinstance(backup_data.get(table), list) else "invalid",
                                }
                                for table in sorted(current_tables | backup_tables)
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                    missing = sorted(current_tables - backup_tables)
                    extra = sorted(backup_tables - current_tables)
                    if missing:
                        st.warning(f"Backup is missing current table(s): {', '.join(missing)}")
                    if extra:
                        st.info(f"Backup contains extra table(s): {', '.join(extra)}")
            except Exception as exc:
                st.error(f"Backup dry-run failed: {exc}")

    st.subheader("Database Info")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Tables", len(dump))
    with col2:
        total_rows = sum(len(v) for v in dump.values())
        st.metric("Rows", total_rows)

    st.caption(f"Database path: `{_DB_PATH}`")

    with st.expander("Table overview", expanded=False):
        for tname, trows in dump.items():
            st.markdown(f"**{tname}** - {len(trows)} row(s)")


# ── Main ─────────────────────────────────────────────────────────────────────


def _hide_streamlit_chrome() -> None:
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"] { display: none !important; height: 0 !important; }
        #MainMenu { display: none !important; }
        footer { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stDecoration"] { display: none !important; }
        [data-testid="stStatusWidget"] { display: none !important; }
        .block-container,
        [data-testid="stMainBlockContainer"] {
            padding-top: 0.5rem !important;
            padding-bottom: 1rem !important;
            max-width: 100% !important;
        }
        section[data-testid="stMain"] { padding-top: 0 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="CIM Management Center", layout="wide")
    _hide_streamlit_chrome()

    if _LAYER == "output":
        st.info("Use the left Management Center page.")
        st.stop()

    st.title(":material/settings: Management Center")
    role = _current_role()
    if role != "admin":
        st.warning(
            f"Read-only mode: current role `{role}` cannot perform management write actions.",
            icon=":material/lock:",
        )
    else:
        st.caption("Current role: `admin`")

    if _is_dev_mode():
        st.info(
            ":material/developer_mode: **DEV mode**. Restart the sidecar with `CIM_DEV_MODE=0` to preview Prod visibility.",
            icon=":material/developer_mode:",
        )
    else:
        st.success(
            ":material/rocket_launch: **PRODUCTION mode**. Only tools with Prod visibility are shown.",
            icon=":material/rocket_launch:",
        )

    try:
        reg = _registry()
    except Exception as exc:
        st.error(f"Could not connect to the management database: {exc}")
        st.stop()
        return

    tab_health, tab_modules, tab_runs, tab_sheets, tab_repairs, tab_audit = st.tabs(
        ["Health", "Tools", "Runs & Usage", "Sheets", "Repairs", "Audit & Database"]
    )

    with tab_health:
        _page_dashboard(reg)

    with tab_modules:
        _page_tools(reg)

    with tab_runs:
        _page_runs(reg)

    with tab_sheets:
        _page_sheets(reg)

    with tab_repairs:
        _page_repairs(reg)

    with tab_audit:
        _page_system(reg)


if __name__ == "__main__":
    main()
