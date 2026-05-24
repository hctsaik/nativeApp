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


def _render_selected_tool_actions(
    reg: PluginRegistry,
    selected_row: dict[str, Any],
    active_rows: list[dict[str, Any]],
    readiness_by_id: dict[str, Any],
    manage_disabled: bool,
) -> None:
    selected_tool_id = str(selected_row["tool_id"])
    selected_readiness = readiness_by_id.get(selected_tool_id)
    plugin_id = selected_tool_id if selected_tool_id.startswith("module_") else None
    sheet_id = selected_tool_id[len("sheet-"):] if selected_tool_id.startswith("sheet-") else None
    selected_sheet_issues = validate_sheet_prod_readiness(_DB_PATH, sheet_id) if sheet_id else []
    is_prod_visible = bool(selected_row["enabled_prod"])

    st.markdown(_tool_header(selected_row))
    status_cols = st.columns(4)
    status_cols[0].metric("Category", selected_readiness.category if selected_readiness else "unknown")
    status_cols[1].metric("Prod visibility", "On" if is_prod_visible else "Off")
    status_cols[2].metric("Active snapshot", "N/A" if sheet_id else (selected_row["active_version"] or "None"))
    status_cols[3].metric(
        "Checks",
        "Needs attention" if selected_sheet_issues or (selected_readiness and selected_readiness.issues) else "Passed",
    )

    if sheet_id and selected_sheet_issues:
        st.warning("This Sheet needs attention before it should be visible in Prod.")
        for issue in selected_sheet_issues:
            st.caption(f"- {issue.label} ({issue.plugin_id}): {issue.issue}")
    elif selected_readiness and selected_readiness.issues:
        st.warning("This tool needs attention before it should be visible in Prod.")
        for issue in selected_readiness.issues:
            st.caption(f"- {issue}")

    if plugin_id:
        preflight = module_preflight(_SCRIPTS_DIR, plugin_id)
        snapshot_diff = module_snapshot_diff(_SCRIPTS_DIR, _DB_PATH, plugin_id)

        if preflight.ok:
            st.success("Publish checks passed.")
        else:
            st.error("Publish checks failed. Fix these before publishing a snapshot.")
            for issue in preflight.issues:
                st.caption(f"- {issue}")

        if snapshot_diff.has_active_snapshot:
            st.caption(
                f"Compared with active snapshot: {len(snapshot_diff.added)} added, "
                f"{len(snapshot_diff.changed)} changed, {len(snapshot_diff.removed)} removed."
            )
        else:
            st.caption(f"No active snapshot yet. {snapshot_diff.current_file_count} files would be published.")

        with st.expander("Changed files", expanded=False):
            st.json(snapshot_diff.summary())

    action_cols = st.columns([1, 1, 1, 1, 1])
    with action_cols[0]:
        if plugin_id and st.button(
            "Create snapshot",
            key=f"create_snapshot_{selected_tool_id}",
            type="primary",
            disabled=manage_disabled or not module_preflight(_SCRIPTS_DIR, plugin_id).ok,
            use_container_width=True,
        ):
            _create_snapshot_dialog(reg, plugin_id, selected_tool_id)
    with action_cols[1]:
        if plugin_id and st.button(
            "Snapshot + Prod",
            key=f"publish_prod_{selected_tool_id}",
            disabled=manage_disabled or not module_preflight(_SCRIPTS_DIR, plugin_id).ok,
            use_container_width=True,
        ):
            _publish_dialog(reg, plugin_id, selected_tool_id)
    with action_cols[2]:
        if sheet_id:
            st.info("Sheet Prod visibility is managed in the Sheets tab.")
        else:
            can_enable_prod = bool(
                selected_readiness
                and selected_readiness.prod_ready
                and (
                    selected_readiness.category != "module"
                    or selected_readiness.has_active_version
                )
            )
            if is_prod_visible:
                if st.button("Turn off Prod", key=f"disable_prod_{selected_tool_id}", disabled=manage_disabled, use_container_width=True):
                    _use_cases(reg).set_tool_prod_enabled(selected_tool_id, False, actor=_actor(), source="prod_control")
                    st.toast("Tool is hidden from Prod. Active snapshot is unchanged.", icon=":material/visibility_off:")
                    st.rerun()
            else:
                if st.button("Enable Prod", key=f"enable_prod_{selected_tool_id}", disabled=manage_disabled or not can_enable_prod, use_container_width=True):
                    _use_cases(reg).set_tool_prod_enabled(selected_tool_id, True, actor=_actor(), source="prod_control")
                    st.toast("Tool is visible in Prod.", icon=":material/check_circle:")
                    st.rerun()
                if not can_enable_prod:
                    st.caption("Create a valid snapshot and resolve readiness issues before enabling Prod visibility.")
    with action_cols[3]:
        if _CONTROL_PORT and st.button("Launch", key=f"launch_{selected_tool_id}", use_container_width=True):
            try:
                _start_tool(selected_tool_id)
                st.toast("Tool launched.", icon=":material/rocket_launch:")
            except Exception as exc:
                st.error(f"Launch failed: {exc}")
        elif not _CONTROL_PORT:
            st.caption("Portal only")
    with action_cols[4]:
        if st.button("Archive", key=f"archive_{selected_tool_id}", disabled=manage_disabled, use_container_width=True):
            _confirm_archive_dialog(reg, selected_tool_id, selected_row["name"])

    order_cols = st.columns([1, 1, 3])
    with order_cols[0]:
        next_order = st.number_input(
            "Order",
            value=int(selected_row["order_index"]),
            min_value=0,
            step=1,
            key=f"order_{selected_tool_id}",
        )
    with order_cols[1]:
        if st.button("Save order", key=f"save_order_{selected_tool_id}", disabled=manage_disabled, use_container_width=True):
            _store().update_tool_order({selected_tool_id: int(next_order)})
            st.toast("Order saved.", icon=":material/check_circle:")
            st.rerun()

    if plugin_id:
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
                    f" - {ver.created_at[:16]}"
                    + (f" - {ver.changelog}" if ver.changelog else "")
                )
                if not ver.is_active and st.button(
                    f"Rollback to #{ver.version_id}",
                    key=f"rollback_{plugin_id}_{ver.version_id}",
                    disabled=manage_disabled,
                ):
                    _confirm_rollback_dialog(reg, plugin_id, ver.version_id)

    with st.expander("Lifecycle", expanded=False):
        st.caption("Archive hides a tool without deleting snapshots. Delete draft is only for unpublished tools.")
        if plugin_id and st.button(
            "Delete unpublished draft",
            key=f"delete_draft_{selected_tool_id}",
            disabled=manage_disabled or bool(selected_row["active_version"]) or bool(selected_row["enabled_prod"]),
        ):
            _confirm_delete_draft_tool_dialog(reg, selected_tool_id, selected_row["name"])


def _page_tools(reg: PluginRegistry) -> None:
    st.header(":material/extension: Tools")
    manage_disabled = not _can_manage()

    if not _DB_PATH.exists():
        st.warning("Database has not been created yet. Start the sidecar first.")
        return

    _render_module_import_and_scaffold(reg, manage_disabled)

    active = _get_active_tool()
    if active and active.get("active"):
        st.info(f"Currently running: `{active['tool_id']}`", icon=":material/play_circle:")

    try:
        rows = _load_tool_rows()
        archived = _load_archived_rows()
    except Exception as exc:
        st.error(f"Could not load tools: {exc}")
        return

    if not rows:
        st.info("No active tools are registered yet. Inactive tools are listed below.")

    readiness_by_id = {item.tool_id: item for item in collect_tool_readiness(_DB_PATH)}

    st.subheader("Tool Actions")
    action_panel = st.container()

    st.subheader("Active Tools")
    active_rows = rows
    search = st.text_input("Search active tools", placeholder="Name or ID", label_visibility="collapsed")
    if search.strip():
        q = search.strip().lower()
        active_rows = [r for r in active_rows if q in r["name"].lower() or q in r["tool_id"].lower()]

    col_category, col_status = st.columns(2)
    with col_category:
        category_filter = st.selectbox(
            "Category",
            ["All", "module", "sheet", "external"],
            key="tool_category_filter",
        )
    with col_status:
        status_filter = st.selectbox(
            "Status",
            ["All", "Visible in Prod", "Checks passed", "Needs attention", "No active snapshot"],
            key="tool_status_filter",
        )

    if category_filter != "All":
        active_rows = [
            r for r in active_rows
            if readiness_by_id.get(r["tool_id"]) and readiness_by_id[r["tool_id"]].category == category_filter
        ]

    if status_filter != "All":
        def _matches_status(row: dict[str, Any]) -> bool:
            readiness = readiness_by_id.get(row["tool_id"])
            if readiness is None:
                return False
            if status_filter == "Visible in Prod":
                return readiness.enabled_prod
            if status_filter == "Checks passed":
                return readiness.prod_ready
            if status_filter == "Needs attention":
                return bool(readiness.issues)
            if status_filter == "No active snapshot":
                return readiness.category == "module" and not readiness.has_active_version
            return True

        active_rows = [r for r in active_rows if _matches_status(r)]

    if not active_rows:
        st.info("No active tools match the current filters.")
        _render_inactive_tools(reg, archived, manage_disabled)
        return

    overview_rows = []
    for row in active_rows:
        readiness = readiness_by_id.get(row["tool_id"])
        category = readiness.category if readiness else ""
        sheet_issues = validate_sheet_prod_readiness(_DB_PATH, row["tool_id"][len("sheet-"):]) if category == "sheet" else []
        issues = sheet_issues if category == "sheet" else (readiness.issues if readiness else [])
        overview_rows.append({
            "tool_id": row["tool_id"],
            "name": row["name"],
            "category": category,
            "prod_visibility": "On" if row["enabled_prod"] else "Off",
            "active_snapshot": "N/A" if category == "sheet" else (row["active_version"] or ""),
            "checks": "Needs attention" if issues else "Passed",
            "issues": "; ".join(
                f"{issue.label} ({issue.plugin_id}): {issue.issue}" for issue in sheet_issues
            ) if sheet_issues else ("; ".join(readiness.issues) if readiness else ""),
        })

    detail_options = [str(row["tool_id"]) for row in overview_rows]
    if st.session_state.get("tools_action_target") not in detail_options:
        st.session_state["tools_action_target"] = detail_options[0]

    table_event = st.dataframe(
        pd.DataFrame(overview_rows),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="tools_table",
        column_config={
            "tool_id": st.column_config.TextColumn("ID"),
            "name": st.column_config.TextColumn("Name"),
            "category": st.column_config.TextColumn("Category"),
            "prod_visibility": st.column_config.TextColumn("Prod visibility"),
            "active_snapshot": st.column_config.TextColumn("Active snapshot"),
            "checks": st.column_config.TextColumn("Checks"),
            "issues": st.column_config.TextColumn("Issues"),
        },
    )

    selected_rows = table_event.selection.rows if table_event.selection.rows else []
    if selected_rows:
        picked_tool_id = str(overview_rows[selected_rows[0]]["tool_id"])
        if picked_tool_id != st.session_state.get("tools_action_target"):
            st.session_state["tools_action_target"] = picked_tool_id
            st.rerun()

    selected_tool_id = st.session_state["tools_action_target"]
    selected_row = next(row for row in active_rows if row["tool_id"] == selected_tool_id)
    with action_panel:
        _render_selected_tool_actions(reg, selected_row, active_rows, readiness_by_id, manage_disabled)

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

    if not plugin_ids:
        st.warning("No modules are available to add to this Sheet.")
        return _sheet_public_steps(steps)

    st.markdown("**Steps**")
    header = st.columns([0.5, 2.2, 3.0, 1.4, 1.8])
    for col, label in zip(header, ["#", "Label", "Module", "Readiness", "Actions"]):
        col.markdown(f"**{label}**")

    remove_idx: int | None = None
    move: tuple[int, int] | None = None
    for i, step in enumerate(steps):
        draft_id = step.setdefault("_draft_id", _sheet_draft_id(key, i))
        cols = st.columns([0.5, 2.2, 3.0, 1.4, 1.8])
        with cols[0]:
            st.markdown(str(i + 1))
        with cols[1]:
            steps[i]["label"] = st.text_input(
                "Step label",
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
        with cols[3]:
            status = readiness_by_step.get(
                (steps[i].get("plugin_id", ""), steps[i].get("label", "")),
                {"status": "Ready"},
            )["status"]
            st.caption(status)
        with cols[4]:
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

    st.divider()
    add_cols = st.columns([3, 3, 1.4])
    with add_cols[0]:
        add_plugin = st.selectbox(
            "Module to add",
            options=plugin_ids,
            format_func=lambda plugin_id: f"{plugin_names.get(plugin_id, plugin_id)} ({plugin_id})",
            key=f"{key}_add_plugin",
        )
    with add_cols[1]:
        add_label = st.text_input("Step label", value=plugin_names.get(add_plugin, add_plugin), key=f"{key}_add_label")
    with add_cols[2]:
        st.write("")
        if st.button("Add step", key=f"{key}_add_step", use_container_width=True):
            steps.append({
                "_draft_id": _sheet_draft_id(key, len(steps)),
                "plugin_id": add_plugin,
                "label": add_label.strip() or plugin_names.get(add_plugin, add_plugin),
            })
            st.rerun()

    return _sheet_public_steps(steps)


def _page_sheets(reg: PluginRegistry) -> None:
    st.header(":material/dashboard: Sheets")
    manage_disabled = not _can_manage()

    plugins = reg.list_plugins()

    with st.expander("Create Sheet", expanded=st.session_state.get("expand_new_sheet", False)):
        new_name = st.text_input("Sheet name", key="new_sheet_name_v2")
        new_desc = st.text_input("Description", key="new_sheet_desc_v2")
        new_steps = _sheet_steps_editor("new_sheet_steps_v2", plugins)
        if st.button("Create Sheet", type="primary", key="save_new_sheet_v2", disabled=manage_disabled):
            if not new_name.strip():
                st.error("Sheet name is required.")
            elif not new_steps:
                st.error("Add at least one step before saving the Sheet.")
            else:
                sheet_id = new_name.strip().lower().replace(" ", "_")
                try:
                    _use_cases(reg).create_or_update_sheet(
                        sheet_id,
                        new_name.strip(),
                        new_desc.strip(),
                        new_steps,
                        actor=_actor(),
                        action="create",
                    )
                    st.toast(f"Created Sheet {new_name.strip()}.", icon=":material/check_circle:")
                    st.session_state.pop("new_sheet_steps_v2", None)
                    st.session_state["expand_new_sheet"] = False
                    st.rerun()
                except Exception as exc:
                    st.error(f"Create Sheet failed: {exc}")

    sync_col, _ = st.columns([1.6, 5])
    with sync_col:
        if st.button("Sync sheet.yaml", icon=":material/sync:", key="sync_sheets_v2", disabled=manage_disabled, use_container_width=True):
            try:
                synced = reg.sync_sheets()
                st.toast(f"Synced: {', '.join(synced)}" if synced else "No sheet.yaml changes found.", icon=":material/check_circle:")
                st.rerun()
            except Exception as exc:
                st.toast(f"Sync failed: {exc}", icon=":material/error:")

    sheets = reg.list_sheets()
    if not sheets:
        st.info("No Sheets yet. Create one above or sync from scripts/sheets/*.yaml.")
        return

    selected_sheet_id = st.selectbox(
        "Sheet",
        options=[sheet.sheet_id for sheet in sheets],
        format_func=lambda sheet_id: next(f"{s.name} ({s.sheet_id})" for s in sheets if s.sheet_id == sheet_id),
        key="selected_sheet_id",
    )
    sheet = next(s for s in sheets if s.sheet_id == selected_sheet_id)
    prod_issues = validate_sheet_prod_readiness(_DB_PATH, sheet.sheet_id)
    draft_key = f"sheet_steps_{sheet.sheet_id}"
    initial_tabs = [{"plugin_id": tab.plugin_id, "label": tab.label} for tab in sheet.tabs]

    summary, readiness_by_step, _ = _sheet_readiness_summary(prod_issues)

    st.subheader(sheet.name)
    action_panel = st.container()

    edit_cols = st.columns([2, 3])
    with edit_cols[0]:
        edit_name = st.text_input("Name", value=sheet.name, key=f"sheet_name_v2_{sheet.sheet_id}")
    with edit_cols[1]:
        edit_desc = st.text_input("Description", value=sheet.description, key=f"sheet_desc_v2_{sheet.sheet_id}")

    steps = _sheet_steps_editor(
        draft_key,
        plugins,
        initial_tabs=initial_tabs,
        readiness_by_step=readiness_by_step,
    )
    draft_steps = st.session_state.get(draft_key, [])
    is_dirty = _sheet_draft_is_dirty(edit_name, edit_desc, draft_steps, sheet, initial_tabs)

    with action_panel:
        meta_cols = st.columns(5)
        meta_cols[0].metric("Sheet ID", sheet.sheet_id)
        meta_cols[1].metric("Steps", len(steps))
        meta_cols[2].metric("Dev", "On" if sheet.enabled_dev else "Off")
        meta_cols[3].metric("Prod", "On" if sheet.enabled_prod else "Off")
        meta_cols[4].metric("Readiness", "Blocked" if prod_issues else "Ready")

        if is_dirty:
            st.warning("Unsaved changes. Save or reset the draft before changing Prod visibility.")
        elif prod_issues:
            st.warning(summary)
        else:
            st.success("Prod ready.")

        action_cols = st.columns([1, 1, 1, 1, 1])
        with action_cols[0]:
            if st.button("Save Sheet", type="primary", key=f"sheet_save_v2_{sheet.sheet_id}", disabled=manage_disabled, use_container_width=True):
                if not edit_name.strip():
                    st.error("Sheet name is required.")
                elif not steps:
                    st.error("Add at least one step before saving the Sheet.")
                else:
                    try:
                        _use_cases(reg).create_or_update_sheet(
                            sheet.sheet_id,
                            edit_name.strip(),
                            edit_desc.strip(),
                            steps,
                            actor=_actor(),
                            action="update",
                        )
                        st.toast("Sheet saved.", icon=":material/check_circle:")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Save Sheet failed: {exc}")
        with action_cols[1]:
            if st.button("Hide in Dev" if sheet.enabled_dev else "Show in Dev", key=f"sheet_dev_v2_{sheet.sheet_id}", disabled=manage_disabled, use_container_width=True):
                _use_cases(reg).set_sheet_dev_enabled(sheet.sheet_id, not sheet.enabled_dev, actor=_actor())
                st.rerun()
        with action_cols[2]:
            if st.button(
                "Prod off" if sheet.enabled_prod else "Prod on",
                key=f"sheet_prod_v2_{sheet.sheet_id}",
                disabled=manage_disabled or is_dirty or (not sheet.enabled_prod and bool(prod_issues)),
                use_container_width=True,
            ):
                try:
                    _use_cases(reg).set_sheet_prod_enabled(sheet.sheet_id, not sheet.enabled_prod, actor=_actor())
                    st.rerun()
                except SheetProdReadinessError as exc:
                    failed_summary, _, failed_details = _sheet_readiness_summary(exc.issues)
                    st.error(failed_summary)
                    if failed_details:
                        st.dataframe(pd.DataFrame(failed_details), use_container_width=True, hide_index=True)
        with action_cols[3]:
            if st.button("Discard edits", key=f"sheet_reset_v2_{sheet.sheet_id}", use_container_width=True):
                st.session_state[draft_key] = _prepare_sheet_draft_steps(draft_key, initial_tabs)
                st.rerun()
        with action_cols[4]:
            if st.button("Delete Sheet", key=f"sheet_delete_v2_{sheet.sheet_id}", disabled=manage_disabled, use_container_width=True):
                _confirm_delete_sheet_dialog(reg, sheet.sheet_id, sheet.name)
    return



def _page_runs(reg: PluginRegistry) -> None:
    st.header(":material/monitoring: Runs & Usage")
    store = _store()
    days = st.slider("Usage window", min_value=1, max_value=90, value=30, step=1)

    st.subheader("Usage Summary")
    usage_rows = store.usage_summary(days=days)
    if usage_rows:
        st.dataframe(pd.DataFrame(usage_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No tool runs have been recorded yet. Launch a tool from the Portal or Tools tab.")

    st.subheader("Recent Runs")
    tool_filter = st.text_input("Filter by tool ID", placeholder="Optional", key="run_tool_filter")
    runs = store.list_tool_run_rows(limit=100, tool_id=tool_filter.strip() or None)
    if runs:
        st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
    else:
        st.caption("No matching runs.")


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
