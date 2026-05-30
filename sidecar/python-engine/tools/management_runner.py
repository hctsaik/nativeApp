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
    from plugin_loader import find_module_folder  # noqa: PLC0415

    try:
        yaml_path = find_module_folder(plugin_id) / "plugin.yaml"
    except Exception:
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


def _render_external_system_register() -> None:
    """No-code: register external task systems (writes config/external_systems.yaml)."""
    import yaml as _yaml  # noqa: PLC0415
    from pathlib import Path as _Path  # noqa: PLC0415

    cfg_path = _Path(__file__).resolve().parent.parent / "config" / "external_systems.yaml"
    try:
        data = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    except Exception:
        data = {}
    systems = (data or {}).get("systems") or []

    st.subheader("🔌 外部系統註冊（宣告式）")
    st.caption("新增的系統寫入 config/external_systems.yaml；資料來源頁載入時自動同步（token 從環境變數讀）。")
    if systems:
        for s in systems:
            _ct = s.get("connector_type")
            _ctlbl = f" · {_ct}" if _ct else " · 自動"
            _maplbl = " · 自訂映射" if s.get("rest_mapping") else ""
            st.markdown(f"- **{s.get('system_name','?')}** — `{s.get('server_host_name','')}` "
                        f"({s.get('target_format','')}{_ctlbl}{_maplbl})")
    else:
        st.caption("（目前無宣告的外部系統）")

    with st.form("ext_sys_register", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("系統名稱", placeholder="iWISC")
        host = col2.text_input("Server host", placeholder="http://localhost:8765")
        col3, col4 = st.columns(2)
        fmt = col3.selectbox("目標格式", ["xanylabeling", "coco", "yolo", "labelme"])
        token_env = col4.text_input("API token 環境變數名", placeholder="IWSC_TOKEN")
        try:
            from plugins.labeling.domain.integrations.registry import available_types  # noqa: PLC0415
            _ctypes = available_types()  # 動態：register_connector 註冊的新協定也會出現
        except Exception:
            _ctypes = ["rest", "file", "fake"]
        ctype = st.selectbox("連接器類型", ["（自動：依 host scheme 推斷）", *_ctypes],
                             help="自動＝http(s)→rest、file://→file、fake://→fake；"
                                  "經 register_connector 註冊的新協定會自動出現於此")
        # 進階：REST 變體的 endpoint/欄位映射（純宣告，免寫 connector class）
        with st.expander("進階：REST 端點 / 欄位映射（接非 iWISC 契約的 REST 系統）", expanded=False):
            st.caption("留白＝沿用內建 iWISC 契約。填了即寫入 rest_mapping，免寫程式碼。")
            mc1, mc2 = st.columns(2)
            rm_list = mc1.text_input("list 路徑", placeholder="/getAntList（預設）")
            rm_detail = mc2.text_input("detail 路徑", placeholder="/getAntTaskDetail（預設）")
            mc3, mc4 = st.columns(2)
            rm_claim = mc3.text_input("claim 路徑", placeholder="/tasks/{ant_id}/claim（預設）")
            rm_method = mc4.selectbox("detail HTTP method", ["POST", "GET"])
            st.caption("回應欄位映射（你的欄位名 → 平台欄位）：")
            fc1, fc2, fc3, fc4 = st.columns(4)
            f_id = fc1.text_input("ant_id ←", placeholder="antID")
            f_active = fc2.text_input("ant_active ←", placeholder="antActive")
            f_period = fc3.text_input("ant_period ←", placeholder="antPeriod")
            f_dl = fc4.text_input("download_url ←", placeholder="download_url")
        if st.form_submit_button("➕ 新增外部系統", type="primary"):
            if not (name and host):
                st.error("系統名稱與 host 為必填。")
            else:
                entry = {"system_name": name, "server_host_name": host, "target_format": fmt}
                if token_env:
                    entry["api_token_env"] = token_env
                if not ctype.startswith("（自動"):
                    entry["connector_type"] = ctype
                _mapping: dict = {}
                if rm_list.strip():
                    _mapping["list_path"] = rm_list.strip()
                if rm_detail.strip():
                    _mapping["detail_path"] = rm_detail.strip()
                if rm_claim.strip():
                    _mapping["claim_path"] = rm_claim.strip()
                if rm_method != "POST":
                    _mapping["detail_method"] = rm_method
                _fields = {k: v.strip() for k, v in
                           {"ant_id": f_id, "ant_active": f_active,
                            "ant_period": f_period, "download_url": f_dl}.items() if v.strip()}
                if _fields:
                    _mapping["fields"] = _fields
                if _mapping:
                    entry["rest_mapping"] = _mapping
                # 以系統名稱為唯一鍵：重註冊同名即更新（含改 host），不留殘項
                systems = [s for s in systems if s.get("system_name") != name]
                systems.append(entry)
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg_path.write_text(_yaml.safe_dump({"systems": systems}, allow_unicode=True),
                                    encoding="utf-8")
                st.success(f"✅ 已新增「{name}」，資料來源頁載入時自動生效。")

    # 一鍵測試連線 + 欄位映射預覽（補「設定後不確定通不通／映射對不對」的摩擦）
    st.markdown("**測試連線 / 欄位映射預覽**")
    # 可從已註冊系統一鍵帶入 host + list 端點 + token + mapping（免手抄）
    _picklabels = ["（手動輸入）"] + [s.get("system_name", "?") for s in systems]
    _pick = st.selectbox("帶入已註冊系統", _picklabels, key="ext_test_pick")
    _picked = next((s for s in systems if s.get("system_name") == _pick), None)
    _pre_host, _pre_path, _pre_tokenenv = "", "/", ""
    _pick_mapping = None
    if _picked:
        _pre_host = _picked.get("server_host_name", "")
        _pick_mapping = _picked.get("rest_mapping")
        _pre_path = (_pick_mapping or {}).get("list_path", "/getAntList")
        _pre_tokenenv = _picked.get("api_token_env", "")
    _tc1, _tc2, _tc3 = st.columns([3, 2, 1])
    _test_host = _tc1.text_input("host", value=_pre_host, placeholder="http://localhost:8765",
                                 key=f"ext_test_host_{_pick}", label_visibility="collapsed")
    _test_path = _tc2.text_input("path", value=_pre_path, placeholder="/api/tasks",
                                 key=f"ext_test_path_{_pick}", label_visibility="collapsed")
    _test_tokenenv = _tc1.text_input("token 環境變數（選填，會帶 Authorization: Bearer）",
                                     value=_pre_tokenenv, placeholder="IWSC_TOKEN",
                                     key=f"ext_test_tokenenv_{_pick}")
    _test_fmt = _tc2.text_input("detail format", value=(_picked or {}).get("target_format", "coco")
                                if _picked else "coco", key=f"ext_test_fmt_{_pick}",
                                help="detail 端點 payload 的 format（多格式系統可調）")
    if _tc3.button("🔌 測試", key="ext_test_btn", use_container_width=True):
        if not _test_host.strip():
            st.warning("請先填入要測試的 host。")
        else:
            try:
                import json as _json  # noqa: PLC0415
                import os as _os  # noqa: PLC0415
                import urllib.request  # noqa: PLC0415
                _url = _test_host.strip().rstrip("/") + "/" + _test_path.strip().lstrip("/")
                _headers = {}
                _tok = _os.environ.get((_test_tokenenv or "").strip()) if _test_tokenenv.strip() else None
                if _tok:
                    _headers["Authorization"] = f"Bearer {_tok}"
                req = urllib.request.Request(_url, method="GET", headers=_headers)
                with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                    body = resp.read(4000).decode("utf-8", "replace")
                _authnote = "（已帶 token）" if _tok else ("（token 環境變數未設定值）"
                                                          if _test_tokenenv.strip() else "")
                st.success(f"✅ 連線成功 HTTP {resp.status} {_authnote} — {_url}")
                # 欄位映射預覽：若回應為 JSON 陣列，套用此系統的 rest_mapping 解析第一筆
                try:
                    _data = _json.loads(body)
                    if isinstance(_data, list) and _data and isinstance(_data[0], dict):
                        from plugins.labeling.domain.integrations.connectors.configurable_rest_connector import (  # noqa: PLC0415,E501
                            map_list_item, resolve_paths)
                        _fields = resolve_paths(_pick_mapping)["fields"]
                        _n = min(3, len(_data))
                        st.caption(f"依欄位映射解析前 {_n} 筆任務（確認 ant_id/狀態是否對上）：")
                        _t0 = None
                        for _i in range(_n):
                            if isinstance(_data[_i], dict):
                                _ti = map_list_item(_data[_i], _fields)
                                _t0 = _t0 or _ti
                                st.json({"ant_id": _ti.ant_id, "ant_active": _ti.ant_active,
                                         "ant_period": _ti.ant_period,
                                         "external_context": _ti.external_context})
                        # detail 端點預覽：用第一筆 ant_id 打 detail_path，確認 download_url 映射
                        _rp = resolve_paths(_pick_mapping)
                        if _t0 and _t0.ant_id and _rp.get("detail_path"):
                            try:
                                _durl = _test_host.strip().rstrip("/") + "/" + _rp["detail_path"].lstrip("/")
                                _fmt = (_test_fmt or "coco").strip()
                                _payload = _json.dumps({"antID": _t0.ant_id, "format": _fmt}).encode()
                                if (_rp.get("detail_method") or "POST").upper() == "GET":
                                    _dreq = urllib.request.Request(
                                        f"{_durl}?antID={_t0.ant_id}&format={_fmt}", method="GET", headers=_headers)
                                else:
                                    _dh = {**_headers, "Content-Type": "application/json"}
                                    _dreq = urllib.request.Request(_durl, data=_payload, method="POST", headers=_dh)
                                with urllib.request.urlopen(_dreq, timeout=5) as _dresp:  # noqa: S310
                                    _dbody = _json.loads(_dresp.read(2000).decode("utf-8", "replace"))
                                _dlkey = _fields.get("download_url", "download_url")
                                _dl = _dbody.get(_dlkey, _dbody.get("download_url", ""))
                                st.caption(f"detail 端點 OK — download_url（映射鍵 `{_dlkey}`）："
                                           f"{'✅ ' + _dl if _dl else '⚠️ 解析為空，請確認 download_url 映射'}")
                            except Exception as _de:  # noqa: BLE001
                                from core import guidance as _g  # noqa: PLC0415
                                _card = _g.diagnose(str(_de))
                                if _card:
                                    st.warning(f"detail 端點：{_card['title']} — {_card['hint']}")
                                else:
                                    st.caption(f"（detail 端點預覽略過：{_de}）")
                    elif isinstance(_data, dict):
                        # 巢狀 envelope（如 {"data":{"items":[...]}}）目前需平面陣列
                        st.info("回應是物件而非任務陣列。若任務清單包在巢狀欄位（如 "
                                "`data.items`），目前 rest_mapping 需要 list 端點直接回傳陣列；"
                                "可調整 list_path 指向回傳陣列的端點。")
                except Exception:  # noqa: BLE001
                    pass
                if body.strip():
                    with st.expander("原始回應（前 800 字）", expanded=False):
                        st.code(body[:800] + ("…" if len(body) >= 800 else ""), language="json")
            except Exception as exc:  # noqa: BLE001
                st.error(f"❌ 連不上：{exc}。請確認 server 已啟動、host/path 正確、token 有效。")


def _render_external_tab(
    reg: PluginRegistry,
    external_rows: list[dict[str, Any]],
    readiness_by_id: dict[str, Any],
    manage_disabled: bool,
) -> None:
    _render_external_system_register()
    st.markdown("---")
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

    tab_usage, tab_sheet_log, tab_stale = st.tabs(["模組使用率", "Sheet 執行記錄", "閒置建議"])

    # ── Tab 1: 模組使用率（點選 Sheet → 顯示該 Sheet 各模組的使用率）────────
    with tab_usage:
        days_map = {"7 天": 7, "30 天": 30, "90 天": 90}
        period = st.radio("時間範圍", list(days_map.keys()), index=1,
                          horizontal=True, label_visibility="collapsed", key="usage_period")
        days = days_map[period]

        # Sheet 選擇
        sheet_rows = store.list_sheet_reference_records()
        sheet_ids = sorted({r["sheet_id"] for r in sheet_rows})
        if not sheet_ids:
            st.info("尚未建立任何 Sheet。請先在 Sheets 頁面新增工作流程。")
        else:
            sheet_names = {r["sheet_id"]: r["sheet_name"] for r in sheet_rows}
            sheet_options = [f"{sheet_names.get(sid, sid)}  ({sid})" for sid in sheet_ids]
            sel_idx = st.selectbox("選擇 Sheet", range(len(sheet_ids)),
                                   format_func=lambda i: sheet_options[i],
                                   key="usage_sheet_sel")
            selected_sheet_id = sheet_ids[sel_idx]

            module_rows = store.module_usage_by_sheet(selected_sheet_id, days=days)
            tool_names = {p.plugin_id: p.name for p in reg.list_plugins()}

            if not module_rows:
                st.info(f"此 Sheet 在過去 {days} 天內無模組執行記錄。")
                st.caption("模組執行完成時，Portal 會自動回報執行結果。")
            else:
                # KPI 總覽
                total = sum(r["run_count"] for r in module_rows)
                completed = sum(r["completed_count"] for r in module_rows)
                failed = sum(r["failed_count"] for r in module_rows)
                rate = f"{completed / total * 100:.0f}%" if total else "—"
                kc = st.columns(3)
                kc[0].metric("總執行次數", total)
                kc[1].metric("成功率", rate)
                kc[2].metric("失敗次數", failed)

                st.divider()

                tdata = []
                for r in module_rows:
                    pid = r["plugin_id"]
                    runs = r["run_count"]
                    comp = r["completed_count"]
                    r_rate = (comp / runs * 100) if runs else 0
                    rate_str = f"{r_rate:.0f}% ⚠" if r_rate < 80 and runs >= 3 else f"{r_rate:.0f}%"
                    tdata.append({
                        "ID": pid,
                        "模組名稱": tool_names.get(pid, pid),
                        "執行次數": runs,
                        "成功率": rate_str,
                        "平均時長": _fmt_ms(r.get("avg_duration_ms")),
                        "最後使用": r.get("last_used_at", "—"),
                    })
                st.dataframe(pd.DataFrame(tdata), use_container_width=True, hide_index=True)

    # ── Tab 2: Sheet 執行記錄（原始 tool_runs，category=sheet）───────────────
    with tab_sheet_log:
        days_map2 = {"7 天": 7, "30 天": 30, "90 天": 90}
        period2 = st.radio("時間範圍", list(days_map2.keys()), index=1,
                           horizontal=True, label_visibility="collapsed", key="log_period")
        days2 = days_map2[period2]

        usage_rows = store.usage_summary(days=days2)
        tool_names2 = {p.plugin_id: p.name for p in reg.list_plugins()}

        if not usage_rows:
            st.info("目前沒有執行記錄。請從 Portal 啟動工具後記錄會自動產生。")
        else:
            total_runs = sum(r["run_count"] for r in usage_rows)
            total_failed = sum(r["failed_count"] for r in usage_rows)
            total_completed = sum(r["completed_count"] for r in usage_rows)
            success_rate = f"{total_completed / total_runs * 100:.0f}%" if total_runs else "—"

            kc = st.columns(4)
            kc[0].metric("總執行次數", total_runs)
            kc[1].metric("成功率", success_rate)
            kc[2].metric("失敗次數", total_failed)
            kc[3].metric("活躍工具", len(usage_rows))

            st.divider()

            summary_data = []
            for r in usage_rows:
                tid = r["tool_id"]
                runs = r["run_count"]
                rate = (r["completed_count"] / runs * 100) if runs else 0
                rate_str = f"{rate:.0f}% ⚠" if rate < 80 and runs >= 3 else f"{rate:.0f}%"
                summary_data.append({
                    "工具名稱": tool_names2.get(tid, tid),
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

            sel_rows = evt.selection.rows
            if not sel_rows:
                st.caption("點選上方工具列查看詳細執行記錄。")
            else:
                selected_tool_id = df_summary.iloc[sel_rows[0]]["_tool_id"]
                selected_tool_name = tool_names2.get(selected_tool_id, selected_tool_id)

                st.divider()
                st.subheader(f"{selected_tool_name} 執行記錄")

                runs = store.list_tool_run_rows(limit=50, tool_id=selected_tool_id)
                if not runs:
                    st.caption("尚無執行記錄。")
                else:
                    run_data = []
                    for r in runs:
                        run_data.append({
                            "時間": r.get("started_at", "—"),
                            "狀態": r.get("status", "—"),
                            "時長": _fmt_ms(r.get("duration_ms")),
                            "執行者": r.get("actor", "—"),
                            "錯誤": r["error_summary"] if r.get("status") == "failed" and r.get("error_summary") else "—",
                        })
                    st.dataframe(pd.DataFrame(run_data), use_container_width=True, hide_index=True)

    # ── Tab 3: 閒置建議（90天未執行的模組）──────────────────────────────────
    with tab_stale:
        stale_days_map = {"30 天": 30, "60 天": 60, "90 天": 90}
        stale_period = st.radio("閒置門檻", list(stale_days_map.keys()), index=2,
                                horizontal=True, label_visibility="collapsed", key="stale_period")
        stale_days = stale_days_map[stale_period]

        stale_rows = store.stale_modules(days=stale_days)
        if not stale_rows:
            st.success(f"所有模組在過去 {stale_days} 天內都有執行記錄，無需清理。")
        else:
            st.warning(
                f"以下 **{len(stale_rows)}** 個模組超過 **{stale_days} 天**未執行，"
                "建議評估是否可停用或移除以降低維護負擔。"
            )
            stale_data = []
            for r in stale_rows:
                last_used = r.get("last_used_at") or "從未執行"
                stale_data.append({
                    "ID": r["tool_id"],
                    "模組名稱": r["name"],
                    "最後執行": last_used,
                    "歷史執行次數": r.get("total_runs", 0),
                    "建議": "停用（可從 Modules 頁重新啟用）",
                })
            st.dataframe(pd.DataFrame(stale_data), use_container_width=True, hide_index=True)
            st.caption(
                "**注意**：停用模組不會刪除資料；可隨時在 Modules 頁面重新啟用。"
                " 確認不再使用後，才建議從 Modules 頁面執行刪除。"
            )


def _render_sandbox_policy() -> None:
    """No-code editor for the load-time plugin sandbox (core/sandbox.py reads
    config/sandbox_policy.yaml). Lets a security admin pick enforce/warn/off and
    extend/relax the deny-list — without env vars or code."""
    import yaml as _yaml  # noqa: PLC0415
    from pathlib import Path as _Path  # noqa: PLC0415

    st.subheader("插件沙箱政策（執行安全）")
    st.caption("第三方/手放模組載入前會靜態掃描危險構造（process/網路/shell、動態執行）。"
               "此處設定即時生效，免改環境變數或程式碼。")
    sp_path = _Path(__file__).resolve().parent.parent / "config" / "sandbox_policy.yaml"
    try:
        _sp = _yaml.safe_load(sp_path.read_text(encoding="utf-8")) if sp_path.exists() else {}
    except Exception:
        _sp = {}
    if not isinstance(_sp, dict):
        _sp = {}

    import os as _os  # noqa: PLC0415
    _env_override = _os.environ.get("CIM_PLUGIN_SANDBOX")
    _modes = ["enforce", "warn", "off"]
    _cur_mode = (_sp.get("mode") or "warn").strip().lower()
    _mode = st.radio(
        "強制模式", _modes,
        index=_modes.index(_cur_mode) if _cur_mode in _modes else 1,
        horizontal=True, key="sbx_mode",
        help="enforce＝有違規拒絕載入；warn＝記錄但放行；off＝跳過掃描",
        disabled=bool(_env_override))
    if _env_override:
        st.warning(f"目前由環境變數 CIM_PLUGIN_SANDBOX={_env_override} 覆蓋，此下拉暫不生效。"
                   "若要改用此 GUI 設定：移除該環境變數（PowerShell：`Remove-Item Env:CIM_PLUGIN_SANDBOX`，"
                   "或在啟動腳本/系統環境變數中刪除）後重啟 app。")

    _c1, _c2 = st.columns(2)
    _bi = _c1.text_input("額外禁用 import（逗號分隔）",
                         value=", ".join(_sp.get("blocked_imports") or []), key="sbx_bi",
                         placeholder="requests, urllib")
    _bc = _c2.text_input("額外禁用呼叫（逗號分隔）",
                         value=", ".join(_sp.get("blocked_calls") or []), key="sbx_bc",
                         placeholder="open")
    _ai = _c1.text_input("信任放行 import（從內建黑名單移除）",
                         value=", ".join(_sp.get("allow_imports") or []), key="sbx_ai",
                         placeholder="socket")
    _ac = _c2.text_input("信任放行呼叫", value=", ".join(_sp.get("allow_calls") or []),
                         key="sbx_ac")
    if st.button("💾 儲存沙箱政策", type="primary", key="sbx_save"):
        def _split(s: str) -> list:
            return [x.strip() for x in (s or "").replace("，", ",").split(",") if x.strip()]
        _sp["mode"] = _mode
        _sp["blocked_imports"] = _split(_bi)
        _sp["blocked_calls"] = _split(_bc)
        _sp["allow_imports"] = _split(_ai)
        _sp["allow_calls"] = _split(_ac)
        try:
            sp_path.parent.mkdir(parents=True, exist_ok=True)
            sp_path.write_text(_yaml.safe_dump(_sp, allow_unicode=True, sort_keys=False),
                               encoding="utf-8")
            st.success(f"✅ 已儲存沙箱政策（模式：{_mode}），立即生效。")
        except Exception as exc:  # noqa: BLE001
            st.error(f"寫入失敗：{exc}")
    st.caption("⚠️ 此為靜態 AST 檢查（載入前防呆），非執行期/OS 級隔離；"
               "高敏環境請搭配 enforce 模式並審查模組來源。")


def _page_permissions(reg: PluginRegistry) -> None:
    import yaml as _yaml  # noqa: PLC0415
    from pathlib import Path as _Path  # noqa: PLC0415

    st.header(":material/lock: Permissions")
    policy_path = _Path(__file__).resolve().parent.parent / "config" / "permissions.yaml"

    # ── 視覺化權限矩陣（no-code：勾選即可，免寫 YAML）────────────────────────
    st.subheader("視覺化權限編輯")
    st.caption("選角色 → 勾選可檢視/可執行的模組 → 儲存。直接寫入 config/permissions.yaml，立即生效。")
    try:
        _policy = _yaml.safe_load(policy_path.read_text(encoding="utf-8")) if policy_path.exists() else {}
    except Exception:
        _policy = {}
    if not isinstance(_policy, dict):
        _policy = {}
    _roles_d = _policy.get("roles") if isinstance(_policy.get("roles"), dict) else {}
    _all_ids = sorted(p.plugin_id for p in reg.list_plugins())
    _role_names = list(_roles_d.keys()) or ["admin"]
    _c1, _c2 = st.columns([2, 2])
    _sel_role = _c1.selectbox("角色", _role_names, key="perm_role_sel")
    _new_role = _c2.text_input("或新增角色", key="perm_new_role", placeholder="operator")
    _role = (_new_role.strip() or _sel_role)
    _rule = _roles_d.get(_role) if isinstance(_roles_d.get(_role), dict) else {}
    _is_all = st.checkbox("完整存取（all：可看可執行全部）", value=bool(_rule.get("all")), key=f"perm_all_{_role}")
    _view_all = ("*" in (_rule.get("view") or []))
    _view_allchk = False
    _view_sel: list = []
    _exec_sel: list = []
    if not _is_all:
        _view_allchk = st.checkbox("可檢視全部模組（view: *）", value=_view_all, key=f"perm_vall_{_role}")
        if not _view_allchk:
            _view_sel = st.multiselect("可檢視的模組（view）", _all_ids,
                                       default=[m for m in (_rule.get("view") or []) if m in _all_ids],
                                       key=f"perm_view_{_role}")
        _exec_sel = st.multiselect("可執行的模組（execute）", _all_ids,
                                   default=[m for m in (_rule.get("execute") or []) if m in _all_ids],
                                   key=f"perm_exec_{_role}")
    if st.button("💾 儲存此角色權限", type="primary", key="perm_save_visual"):
        _new_rule: dict = {}
        if _is_all:
            _new_rule["all"] = True
        else:
            _new_rule["view"] = ["*"] if _view_allchk else _view_sel
            _new_rule["execute"] = _exec_sel
        _roles_d[_role] = _new_rule
        _policy["roles"] = _roles_d
        _policy.setdefault("default_policy", "allow")
        try:
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text(_yaml.safe_dump(_policy, allow_unicode=True, sort_keys=False),
                                   encoding="utf-8")
            st.success(f"✅ 已更新角色「{_role}」權限，立即生效。")
        except Exception as exc:  # noqa: BLE001
            st.error(f"寫入失敗：{exc}")

    # 以角色視角預覽：此角色實際可見/可執行哪些模組（讀目前已存的政策）
    with st.expander(f"👁 預覽：角色「{_role}」實際可存取的模組", expanded=False):
        from core.rbac import is_allowed as _is_allowed  # noqa: PLC0415
        _prev = [{"模組": _m,
                  "可檢視": "✅" if _is_allowed(_policy, _role, _m, "view") else "—",
                  "可執行": "✅" if _is_allowed(_policy, _role, _m, "execute") else "—"}
                 for _m in _all_ids]
        st.dataframe(pd.DataFrame(_prev), use_container_width=True, hide_index=True)
    st.markdown("---")

    # ── 進階：直接編 YAML（讀/寫 config/permissions.yaml）────────────────────
    st.subheader("進階：直接編輯 permissions.yaml")
    st.caption(
        "編輯後按「儲存」即生效（由 core/rbac.py 在每次執行前強制檢查；"
        "角色來自 CIM_USER_ROLE）。schema：default_policy: allow|deny；roles.<role>.{all|view|execute}。"
    )
    default_policy = "default_policy: allow\nroles:\n  admin:\n    all: true\n"
    current = policy_path.read_text(encoding="utf-8") if policy_path.exists() else default_policy
    edited = st.text_area("permissions.yaml", value=current, height=280, key="perm_yaml")
    if st.button("💾 儲存權限政策", type="primary", key="perm_save"):
        try:
            parsed = _yaml.safe_load(edited)
            if parsed is not None and not isinstance(parsed, dict):
                raise ValueError("最外層必須是物件（含 default_policy / roles）")
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text(edited, encoding="utf-8")
            st.success("✅ 已儲存，立即生效。")
        except Exception as exc:  # noqa: BLE001
            st.error(f"YAML 格式錯誤，未儲存：{exc}")
    st.markdown("---")

    # ── 插件沙箱政策（執行安全，no-code）──────────────────────────────────────
    _render_sandbox_policy()
    st.markdown("---")

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

    tab_health, tab_modules, tab_runs, tab_sheets, tab_perms, tab_repairs, tab_audit = st.tabs(
        ["Health", "Tools", "Runs & Usage", "Sheets", "Permissions", "Repairs", "Audit & Database"]
    )

    with tab_health:
        _page_dashboard(reg)

    with tab_modules:
        _page_tools(reg)

    with tab_runs:
        _page_runs(reg)

    with tab_sheets:
        _page_sheets(reg)

    with tab_perms:
        _page_permissions(reg)

    with tab_repairs:
        _page_repairs(reg)

    with tab_audit:
        _page_system(reg)


if __name__ == "__main__":
    main()
