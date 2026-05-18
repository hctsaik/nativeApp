from __future__ import annotations

import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import streamlit as st

_ENGINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ENGINE_DIR))

from plugin_registry import PluginRegistry, _is_dev_mode  # noqa: E402

LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
_DB_PATH = LOG_DIR / "data" / "tools.sqlite"
_SCRIPTS_DIR = _ENGINE_DIR / "scripts"
_LAYER = os.environ.get("CIM_TOOL_LAYER", "input")
_CONTROL_PORT = os.environ.get("CIM_CONTROL_PORT", "")


def _registry() -> PluginRegistry:
    return PluginRegistry(db_path=_DB_PATH, scripts_dir=_SCRIPTS_DIR)


def _category_badge(tool_id: str) -> str:
    if tool_id.startswith("sheet_") or tool_id.startswith("sheet-"):
        return "📄 頁面"
    if tool_id.startswith("management-"):
        return "⚙️ 管理"
    return "🧩 模組"


def _load_tool_rows() -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT t.tool_id, t.name, t.enabled, t.enabled_prod, t.order_index,
                  tv.version AS active_version, tv.created_at AS published_at
           FROM tools t
           LEFT JOIN tool_versions tv ON tv.tool_id = t.tool_id AND tv.is_active = 1
           WHERE t.enabled = 1 AND t.tool_id NOT LIKE 'management-%'
           ORDER BY t.order_index, t.name"""
    ).fetchall()
    conn.close()
    return rows


def _load_archived_rows() -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT t.tool_id, t.name, t.enabled_prod, t.order_index,
                  tv.version AS active_version
           FROM tools t
           LEFT JOIN tool_versions tv ON tv.tool_id = t.tool_id AND tv.is_active = 1
           WHERE t.enabled = 0 AND t.tool_id NOT LIKE 'management-%'
           ORDER BY t.name"""
    ).fetchall()
    conn.close()
    return rows


def _set_tool_enabled(tool_id: str, enabled: bool) -> None:
    c = sqlite3.connect(str(_DB_PATH))
    c.execute("UPDATE tools SET enabled=? WHERE tool_id=?", (1 if enabled else 0, tool_id))
    c.commit()
    c.close()


def _set_tool_prod(tool_id: str, enabled: bool) -> None:
    c = sqlite3.connect(str(_DB_PATH))
    c.execute("UPDATE tools SET enabled_prod=? WHERE tool_id=?", (1 if enabled else 0, tool_id))
    c.commit()
    c.close()


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


def _publish_to_prod(reg: PluginRegistry, plugin_id: str, tool_id: str) -> str:
    """One-click: publish plugin version + enable prod in both tables."""
    vid = reg.publish(plugin_id, changelog="一鍵發布", author="管理員")
    _set_tool_prod(tool_id, True)
    return vid


# ── Page: Unified Tool Management ────────────────────────────────────────────


def _tool_header(row: sqlite3.Row) -> str:
    """Build the expander label: badge + name + tool_id + version chip + prod status."""
    badge = _category_badge(row["tool_id"])
    ver = row["active_version"]
    is_prod = bool(row["enabled_prod"])
    ver_chip = f"`v{ver}`" if ver else "`未發布`"
    prod_chip = "  🟢 **PROD**" if is_prod else ""
    return f"{badge} **{row['name']}**  `{row['tool_id']}`  ·  {ver_chip}{prod_chip}"


def _page_tools(reg: PluginRegistry) -> None:
    st.header(":material/build: 工具管理")

    if not _DB_PATH.exists():
        st.warning("資料庫尚未建立，請先啟動 sidecar。")
        return

    # ── 系統狀態 ──────────────────────────────────────────────────────────
    active = _get_active_tool()
    if active and active.get("active"):
        st.info(f":material/play_circle: 目前執行中：`{active['tool_id']}`", icon=":material/play_circle:")

    try:
        rows = _load_tool_rows()
    except Exception as exc:
        st.error(f"讀取工具失敗：{exc}")
        return

    if not rows:
        st.info("目前沒有已啟用的工具。")
        return

    # ── 搜尋 ──────────────────────────────────────────────────────────────
    search = st.text_input("🔍 搜尋工具", placeholder="輸入名稱或 ID…", label_visibility="collapsed")
    if search.strip():
        q = search.strip().lower()
        rows = [r for r in rows if q in r["name"].lower() or q in r["tool_id"].lower()]
    if not rows:
        st.info("沒有符合的工具。")
        return

    # ── 批次操作 ──────────────────────────────────────────────────────────
    tool_ids = [r["tool_id"] for r in rows]
    name_map = {r["tool_id"]: r["name"] for r in rows}

    with st.expander("⚡ 批次操作", expanded=False):
        bulk_selected = st.multiselect(
            "選擇工具",
            options=tool_ids,
            format_func=lambda x: f"{_category_badge(x)} {name_map.get(x, x)}",
            placeholder="選擇要批次操作的工具…",
        )
        col_pub, col_unpub = st.columns(2)
        on_label = "🚀 批次發布至 PROD" if _is_dev_mode() else "✅ 批次啟用 PROD"
        off_label = "↩ 批次取消發布" if _is_dev_mode() else "⛔ 批次停用 PROD"
        with col_pub:
            if st.button(on_label, disabled=not bulk_selected, use_container_width=True):
                for tid in bulk_selected:
                    _set_tool_prod(tid, True)
                st.toast(f"已發布 {len(bulk_selected)} 個工具至 Prod", icon=":material/check_circle:")
                st.rerun()
        with col_unpub:
            if st.button(off_label, disabled=not bulk_selected, use_container_width=True):
                for tid in bulk_selected:
                    _set_tool_prod(tid, False)
                st.toast(f"已取消 {len(bulk_selected)} 個工具的 Prod 發布", icon=":material/check_circle:")
                st.rerun()

    # ── 排序編輯 ──────────────────────────────────────────────────────────
    with st.expander("↕ 排序", expanded=False):
        st.caption("設定工具在 Portal 下拉選單中的顯示順序（數字小的排前面）")
        order_changes: dict[str, int] = {}
        for row in rows:
            col_name, col_num = st.columns([5, 1])
            with col_name:
                st.markdown(f"{_category_badge(row['tool_id'])} {row['name']}")
            with col_num:
                order_changes[row["tool_id"]] = st.number_input(
                    "順序",
                    value=int(row["order_index"]),
                    min_value=0,
                    step=1,
                    key=f"order_{row['tool_id']}",
                    label_visibility="collapsed",
                )
        if st.button("儲存排序", type="primary"):
            c = sqlite3.connect(str(_DB_PATH))
            for tid, idx in order_changes.items():
                c.execute("UPDATE tools SET order_index=? WHERE tool_id=?", (idx, tid))
            c.commit()
            c.close()
            st.toast("已儲存排序", icon=":material/check_circle:")
            st.rerun()

    st.divider()

    # ── 工具卡片列表 ──────────────────────────────────────────────────────
    for row in rows:
        tool_id = row["tool_id"]
        plugin_id = tool_id if tool_id.startswith("module_") else None
        is_prod = bool(row["enabled_prod"])

        with st.expander(_tool_header(row), expanded=False):

            # 測試啟動
            if _CONTROL_PORT:
                if st.button("🚀 測試啟動", key=f"launch_{tool_id}"):
                    try:
                        _start_tool(tool_id)
                        st.toast(f"已啟動「{row['name']}」，請切換至工具視窗", icon=":material/rocket_launch:")
                    except Exception as exc:
                        st.error(f"啟動失敗：{exc}")

            # 版本管理（僅模組有此區塊）
            if plugin_id:
                st.divider()
                try:
                    versions = reg.list_versions(plugin_id)

                    col_pub, col_prod = st.columns(2)
                    with col_pub:
                        if st.button(
                            "🚀 發布到 Prod",
                            key=f"publish_prod_{plugin_id}",
                            type="primary",
                            use_container_width=True,
                        ):
                            try:
                                vid = _publish_to_prod(reg, plugin_id, tool_id)
                                st.toast(f"已發布版本 #{vid}，PROD 已啟用", icon=":material/check_circle:")
                                st.rerun()
                            except Exception as exc:
                                st.toast(f"發布失敗：{exc}", icon=":material/error:")
                    with col_prod:
                        if is_prod:
                            if st.button("↩ 取消發布", key=f"unpub_{tool_id}", use_container_width=True):
                                try:
                                    _set_tool_prod(tool_id, False)
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"更新失敗：{exc}")
                        elif not _is_dev_mode():
                            if st.button("⛔ PROD 已停用", key=f"prod_{tool_id}", use_container_width=True):
                                try:
                                    _set_tool_prod(tool_id, True)
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"更新失敗：{exc}")

                    if versions:
                        with st.expander("📋 版本歷史", expanded=False):
                            for ver in versions:
                                active_badge = "  🟢 **目前版本**" if ver.is_active else ""
                                st.markdown(
                                    f"`v{ver.version}` #{ver.version_id}{active_badge}"
                                    f"  ·  {ver.created_at[:16]}"
                                    + (f"  ·  {ver.changelog}" if ver.changelog else "")
                                )
                                if not ver.is_active:
                                    if st.button(
                                        "↩ 回溯至此版本",
                                        key=f"rollback_{plugin_id}_{ver.version_id}",
                                    ):
                                        reg.rollback(plugin_id, ver.version_id)
                                        st.toast(f"已回溯至版本 #{ver.version_id}", icon=":material/check_circle:")
                                        st.rerun()
                except Exception:
                    st.caption("（尚無版本記錄）")

            # 封存
            st.divider()
            if st.button(
                "📦 移至封存",
                key=f"archive_{tool_id}",
                help="封存後此工具不再出現於 Portal，可在下方「已封存」區段還原",
            ):
                _set_tool_enabled(tool_id, False)
                st.toast(f"已封存「{row['name']}」", icon=":material/archive:")
                st.rerun()

    # ── 已封存工具 ────────────────────────────────────────────────────────
    try:
        archived = _load_archived_rows()
    except Exception:
        archived = []

    if archived:
        st.divider()
        with st.expander(f"📦 已封存的工具（{len(archived)}）", expanded=False):
            for row in archived:
                tool_id = row["tool_id"]
                ver = row["active_version"]
                ver_chip = f"v{ver}" if ver else "未發布"
                col_info, col_restore = st.columns([5, 1])
                with col_info:
                    st.markdown(
                        f"{_category_badge(tool_id)} **{row['name']}**  `{tool_id}`  ·  `{ver_chip}`"
                    )
                with col_restore:
                    if st.button("還原", key=f"restore_{tool_id}"):
                        _set_tool_enabled(tool_id, True)
                        st.toast(f"已還原「{row['name']}」", icon=":material/unarchive:")
                        st.rerun()


# ── Sheet tab editor ──────────────────────────────────────────────────────────


def _sheet_tab_editor(key: str, plugins: list, initial_tabs: list[dict] | None = None) -> None:
    if key not in st.session_state:
        st.session_state[key] = list(initial_tabs or [])

    tabs_draft: list[dict] = st.session_state[key]
    plugin_ids = [p.plugin_id for p in plugins]
    plugin_names = {p.plugin_id: p.name for p in plugins}

    if not plugin_ids:
        st.warning("尚無已登記的外掛，請先啟動 sidecar 讓模組自動登記。")
        return

    to_remove = None
    for i, tab in enumerate(tabs_draft):
        cols = st.columns([3, 4, 1])
        with cols[0]:
            tabs_draft[i]["label"] = st.text_input(
                "分頁標籤",
                value=tab.get("label", ""),
                key=f"{key}_label_{i}",
                label_visibility="collapsed",
                placeholder="分頁標籤",
            )
        with cols[1]:
            current = tab.get("plugin_id", plugin_ids[0])
            idx = plugin_ids.index(current) if current in plugin_ids else 0
            tabs_draft[i]["plugin_id"] = st.selectbox(
                "外掛",
                options=plugin_ids,
                format_func=lambda x: f"{x} — {plugin_names.get(x, '')}",
                index=idx,
                key=f"{key}_plugin_{i}",
                label_visibility="collapsed",
            )
        with cols[2]:
            if st.button("✕", key=f"{key}_del_{i}"):
                to_remove = i

    if to_remove is not None:
        tabs_draft.pop(to_remove)
        st.rerun()

    if st.button("＋ 新增分頁", key=f"{key}_add"):
        tabs_draft.append({"plugin_id": plugin_ids[0], "label": "新分頁"})
        st.rerun()


# ── Page: Sheet Composition ───────────────────────────────────────────────────


def _page_sheets(reg: PluginRegistry) -> None:
    st.header(":material/dashboard: 頁面（Sheet）")

    plugins = reg.list_plugins()

    # ── Create new sheet ──────────────────────────────────────────────────
    with st.expander("＋ 新增頁面", expanded=st.session_state.get("expand_new_sheet", False)):
        new_name = st.text_input("頁面名稱", key="new_sheet_name")
        new_desc = st.text_input("描述（選填）", key="new_sheet_desc")
        st.markdown("**分頁組合：**")
        _sheet_tab_editor("new_sheet_tabs", plugins)

        if st.button("儲存新頁面", type="primary", key="save_new_sheet"):
            if not new_name.strip():
                st.error("請輸入頁面名稱。")
            else:
                sheet_id = new_name.strip().lower().replace(" ", "_")
                tabs = st.session_state.get("new_sheet_tabs", [])
                try:
                    reg.create_or_update_sheet(sheet_id, new_name.strip(), new_desc.strip(), tabs)
                    st.toast(f"已建立頁面「{new_name}」", icon=":material/check_circle:")
                    st.session_state.pop("new_sheet_tabs", None)
                    st.session_state["expand_new_sheet"] = False
                    st.rerun()
                except Exception as exc:
                    st.error(f"建立失敗：{exc}")

    # ── Sync from yaml ────────────────────────────────────────────────────
    col_sync, _ = st.columns([2, 5])
    with col_sync:
        if st.button("從 sheet.yaml 同步", icon=":material/sync:", key="sync_sheets"):
            try:
                synced = reg.sync_sheets()
                if synced:
                    st.toast(f"已同步：{', '.join(synced)}", icon=":material/check_circle:")
                else:
                    st.toast("沒有找到任何 sheet.yaml", icon=":material/info:")
                st.rerun()
            except Exception as exc:
                st.toast(f"同步失敗：{exc}", icon=":material/error:")

    # ── Existing sheets ───────────────────────────────────────────────────
    sheets = reg.list_sheets()
    if not sheets:
        st.info("目前沒有已定義的頁面。可按上方「新增頁面」，或在 scripts/sheets/ 建立 sheet.yaml 後同步。")
        return

    for sheet in sheets:
        edit_key = f"editing_sheet_{sheet.sheet_id}"
        is_editing = st.session_state.get(edit_key, False)

        with st.expander(f"📄 **{sheet.name}**  `{sheet.sheet_id}`", expanded=is_editing):
            if not is_editing:
                st.markdown(f"**描述：** {sheet.description or '—'}")

                # Dev / Prod toggles
                col_dev, col_prod = st.columns(2)
                with col_dev:
                    dev_label = "✅ Dev 已啟用" if sheet.enabled_dev else "⛔ Dev 已停用"
                    if st.button(
                        "Dev 停用" if sheet.enabled_dev else "Dev 啟用",
                        key=f"sheet_dev_{sheet.sheet_id}",
                    ):
                        reg.set_sheet_enabled(sheet.sheet_id, not sheet.enabled_dev, mode="dev")
                        st.rerun()
                    st.caption(dev_label)
                with col_prod:
                    prod_label = "✅ Prod 已啟用" if sheet.enabled_prod else "⛔ Prod 未啟用"
                    if st.button(
                        "Prod 停用" if sheet.enabled_prod else "Prod 啟用",
                        key=f"sheet_prod_{sheet.sheet_id}",
                    ):
                        reg.set_sheet_enabled(sheet.sheet_id, not sheet.enabled_prod, mode="prod")
                        st.rerun()
                    st.caption(prod_label)

                if sheet.tabs:
                    st.markdown("**分頁：**")
                    for tab in sheet.tabs:
                        st.markdown(f"  {tab.tab_order + 1}. **{tab.label}** `{tab.plugin_id}`")

                col_edit, col_del, _ = st.columns([1, 1, 4])
                with col_edit:
                    if st.button("編輯", key=f"btn_edit_{sheet.sheet_id}"):
                        st.session_state[edit_key] = True
                        st.session_state[f"edit_tabs_{sheet.sheet_id}"] = [
                            {"plugin_id": t.plugin_id, "label": t.label} for t in sheet.tabs
                        ]
                        st.rerun()
                with col_del:
                    if st.button("刪除", key=f"btn_del_{sheet.sheet_id}"):
                        reg.delete_sheet(sheet.sheet_id)
                        st.toast(f"已刪除「{sheet.name}」", icon=":material/check_circle:")
                        st.rerun()
            else:
                edit_name = st.text_input("頁面名稱", value=sheet.name, key=f"edit_name_{sheet.sheet_id}")
                edit_desc = st.text_input("描述", value=sheet.description, key=f"edit_desc_{sheet.sheet_id}")
                st.markdown("**分頁組合：**")
                _sheet_tab_editor(f"edit_tabs_{sheet.sheet_id}", plugins)

                col_save, col_cancel, _ = st.columns([1, 1, 4])
                with col_save:
                    if st.button("儲存", type="primary", key=f"btn_save_{sheet.sheet_id}"):
                        tabs = st.session_state.get(f"edit_tabs_{sheet.sheet_id}", [])
                        try:
                            reg.create_or_update_sheet(sheet.sheet_id, edit_name, edit_desc, tabs)
                            st.toast(f"已更新「{edit_name}」", icon=":material/check_circle:")
                            st.session_state[edit_key] = False
                            st.session_state.pop(f"edit_tabs_{sheet.sheet_id}", None)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"儲存失敗：{exc}")
                with col_cancel:
                    if st.button("取消", key=f"btn_cancel_{sheet.sheet_id}"):
                        st.session_state[edit_key] = False
                        st.session_state.pop(f"edit_tabs_{sheet.sheet_id}", None)
                        st.rerun()


# ── Page: Permissions ────────────────────────────────────────────────────────


def _page_permissions(reg: PluginRegistry) -> None:
    st.header(":material/lock: 權限設定")
    st.info(
        "此功能為 Placeholder。目前所有使用者均以 `admin` 角色執行，"
        "權限設定將於 Production 環境的 Web Service 整合後生效。"
    )

    st.markdown("**已定義角色：**")
    with reg._connect() as conn:
        roles = conn.execute("SELECT role_id, name, description FROM roles").fetchall()
    for r in roles:
        st.markdown(f"- **{r['role_id']}** ({r['name']})：{r['description'] or '—'}")

    st.markdown("---")
    st.markdown("**外掛權限矩陣（目前設定）：**")

    plugins = reg.list_plugins()
    if not plugins:
        st.info("尚無外掛。")
        return

    with reg._connect() as conn:
        perms = conn.execute(
            "SELECT plugin_id, role_id, can_view, can_execute FROM plugin_permissions ORDER BY plugin_id, role_id"
        ).fetchall()

    if not perms:
        st.caption("尚無自訂權限列。（所有角色預設完整存取）")
    else:
        table = {
            "外掛": [r["plugin_id"] for r in perms],
            "角色": [r["role_id"] for r in perms],
            "可查看": ["✅" if r["can_view"] else "❌" for r in perms],
            "可執行": ["✅" if r["can_execute"] else "❌" for r in perms],
        }
        st.dataframe(table, use_container_width=True)


# ── Page: System / Backup ────────────────────────────────────────────────────


def _page_system() -> None:
    import datetime
    import json as _json

    st.header(":material/storage: 系統")

    st.subheader("資料庫備份")

    if not _DB_PATH.exists():
        st.warning("資料庫尚未建立，請先啟動 sidecar。")
        return

    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        dump: dict[str, list] = {}
        for t in tables:
            name = t["name"]
            rows = conn.execute(f"SELECT * FROM [{name}]").fetchall()  # noqa: S608
            dump[name] = [dict(r) for r in rows]
        conn.close()
    except Exception as exc:
        st.error(f"讀取資料庫失敗：{exc}")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = _json.dumps(dump, ensure_ascii=False, indent=2, default=str)

    st.download_button(
        label="📥 下載資料庫備份（JSON）",
        data=payload,
        file_name=f"cim_db_backup_{ts}.json",
        mime="application/json",
        use_container_width=True,
    )

    st.divider()
    st.subheader("資料庫資訊")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("資料表數量", len(dump))
    with col2:
        total_rows = sum(len(v) for v in dump.values())
        st.metric("資料列總數", total_rows)

    st.caption(f"資料庫路徑：`{_DB_PATH}`")

    with st.expander("資料表概覽", expanded=False):
        for tname, trows in dump.items():
            st.markdown(f"**{tname}** — {len(trows)} 列")


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
    st.set_page_config(page_title="CIM 管理中心", layout="wide")
    _hide_streamlit_chrome()

    if _LAYER == "output":
        st.info("請在左側頁面操作。")
        st.stop()

    st.title(":material/settings: 管理中心")

    if _is_dev_mode():
        st.info(
            ":material/developer_mode: **DEV 模式**｜切換到 Prod 模式：重啟 sidecar 時加上 `CIM_DEV_MODE=0`",
            icon=":material/developer_mode:",
        )
    else:
        st.success(
            ":material/rocket_launch: **PRODUCTION 模式**｜僅顯示 Prod 已啟用的工具",
            icon=":material/rocket_launch:",
        )

    try:
        reg = _registry()
    except Exception as exc:
        st.error(f"無法連接資料庫：{exc}")
        st.stop()
        return

    tab_tools, tab_sheets, tab_permissions, tab_system = st.tabs(
        ["工具管理", "頁面（Sheet）", "權限設定", "系統"]
    )

    with tab_tools:
        _page_tools(reg)

    with tab_sheets:
        _page_sheets(reg)

    with tab_permissions:
        _page_permissions(reg)

    with tab_system:
        _page_system()


if __name__ == "__main__":
    main()
