from __future__ import annotations

import importlib.util as _ilu
import subprocess
import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_026_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_ui_spec = _ilu.spec_from_file_location("_ui_components", _HERE.parents[3] / "scripts" / "shared" / "ui_components.py")
_ui = _ilu.module_from_spec(_ui_spec)
_ui_spec.loader.exec_module(_ui)

_DEFAULT_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"]

_ANT_ACTIVE_LABEL = {0: "待標注", 1: "標注中", 2: "已完成"}
_ANT_ACTIVE_ICON  = {0: "⚪", 1: "🟠", 2: "🟢"}


def _get_service():
    import os
    from plugins.labeling.domain.services import AnnotationService
    from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
    ws_path = _cfg.get_annotation_workspace_path()
    return AnnotationService(AnnotationWorkspace(ws_path))


def _format_context(ctx: dict) -> str:
    if not ctx:
        return ""
    parts = [f"{k}: {v}" for k in ("lot_id", "eqp_id", "recipe") if k in ctx]
    if not parts:
        parts = [f"{k}: {v}" for k, v in list(ctx.items())[:3]]
    return " | ".join(parts)


def _browse_folder() -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "import tkinter as tk; from tkinter import filedialog; "
             "root=tk.Tk(); root.withdraw(); root.wm_attributes('-topmost',True); "
             "p=filedialog.askdirectory(title='選擇圖片資料夾'); "
             "root.destroy(); print(p or '',end='')"],
            capture_output=True, text=True, timeout=60,
        )
        return result.stdout.strip()
    except Exception:
        return ""


# ─── 各模式 UI ────────────────────────────────────────────────────────────────

def _render_local(cfg: dict) -> dict:
    if "_026_folder_chosen" in st.session_state:
        st.session_state["m026_folder_path"] = st.session_state.pop("_026_folder_chosen")
    if "m026_folder_path" not in st.session_state:
        st.session_state["m026_folder_path"] = cfg.get("last_folder_path", "")

    path_col, btn_col = st.columns([5, 1])
    with path_col:
        folder_path = st.text_input("資料夾路徑", key="m026_folder_path",
                                    placeholder="C:/path/to/images")
    with btn_col:
        st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
        if st.button("📂 瀏覽", use_container_width=True, key="m026_browse"):
            chosen = _browse_folder()
            if chosen:
                st.session_state["_026_folder_chosen"] = chosen
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    if "m026_recursive" not in st.session_state:
        st.session_state["m026_recursive"] = cfg.get("recursive_scan", True)
    recursive = st.checkbox("遞迴掃描子資料夾", key="m026_recursive")

    if "m026_exts" not in st.session_state:
        st.session_state["m026_exts"] = cfg.get("image_extensions", _DEFAULT_EXTENSIONS)
    exts = st.multiselect("允許的圖片副檔名", options=_DEFAULT_EXTENSIONS, key="m026_exts")

    return {
        "mode": "local",
        "folder_path": folder_path,
        "recursive": recursive,
        "extensions": exts or _DEFAULT_EXTENSIONS,
        "manifest_name": Path(folder_path).name if folder_path.strip() else "",
    }


def _render_remote(cfg: dict) -> dict:
    if "m026_svc_url" not in st.session_state:
        st.session_state["m026_svc_url"] = cfg.get("service_url", "")

    service_url = st.text_input("Service Base URL", key="m026_svc_url",
                                placeholder="http://api.internal:8080")

    if not service_url:
        st.info("請填入 Service Base URL 後執行。")
        return {"mode": "remote", "service_url": "", "dataset_id": "", "dataset_name": "", "overwrite": False}

    col_r, _ = st.columns([1, 4])
    with col_r:
        if st.button("🔄 載入資料集清單", key="m026_refresh_ds"):
            st.session_state.pop("m026_datasets", None)

    datasets: list[dict] = st.session_state.get("m026_datasets", [])
    if not datasets:
        with st.spinner("取得資料集清單…"):
            try:
                import importlib.util as _iu2
                _proc19_spec = _iu2.spec_from_file_location(
                    "_019_process", _HERE.parent / "module_019" / "019_process.py")
                _proc19 = _iu2.module_from_spec(_proc19_spec)
                _proc19_spec.loader.exec_module(_proc19)
                datasets = _proc19.list_datasets(service_url)
                st.session_state["m026_datasets"] = datasets
            except Exception as exc:
                st.error(f"❌ {exc}")
                return {"mode": "remote", "service_url": service_url, "dataset_id": "", "dataset_name": "", "overwrite": False}

    if not datasets:
        st.warning("此 Service 目前沒有可用的資料集。")
        return {"mode": "remote", "service_url": service_url, "dataset_id": "", "dataset_name": "", "overwrite": False}

    ds_map = {f"{d['name']} ({d.get('item_count', '?')} 張)": d for d in datasets}
    sel_label = st.selectbox("資料集", list(ds_map.keys()), key="m026_ds_select")
    sel = ds_map[sel_label]
    overwrite = st.checkbox("重新下載（覆蓋現有）", value=False, key="m026_overwrite")

    return {
        "mode": "remote",
        "service_url": service_url,
        "dataset_id": sel["dataset_id"],
        "dataset_name": sel["name"],
        "overwrite": overwrite,
    }


def _render_iwsc() -> dict:
    try:
        service = _get_service()
        # No-code: register any external systems declared in
        # config/external_systems.yaml (idempotent — edit YAML to add systems).
        try:
            from core.external_systems import load_declared_systems  # noqa: PLC0415
            service.sync_external_systems(load_declared_systems())
        except Exception:
            pass
        tenants = service.list_tenants()
    except Exception as exc:
        st.error(f"❌ 無法載入 Tenant 清單：{exc}")
        return {"mode": "iwsc"}

    if not tenants:
        st.warning(
            "尚無外部系統。可在 `config/external_systems.yaml` 宣告（編輯即生效），"
            "或透過 annotation MCP `register_tenant` 註冊。"
        )
        return {"mode": "iwsc"}

    tenant_map = {f"{t['system_name']} ({t['tenant_id'][:8]}…)": t for t in tenants}
    sel_label = st.selectbox("外部系統", list(tenant_map.keys()), key="m026_tenant")
    tenant = tenant_map[sel_label]
    tenant_id = tenant["tenant_id"]

    user_id = st.text_input("您的使用者 ID（工號）", key="m026_user_id", placeholder="user001")
    st.caption("有任務限制的任務僅授權人員可認領。")

    col_btn, _ = st.columns([2, 5])
    with col_btn:
        if st.button("🔄 查看任務清單", key="m026_fetch"):
            if not user_id.strip():
                st.session_state["m026_task_err"] = "請先填入使用者 ID"
            else:
                try:
                    tasks = service.get_ant_list(tenant_id)
                    try:
                        local_tasks = service.list_tasks(tenant_id)
                        local_state = {t["ant_id"]: t["ant_active"] for t in local_tasks}
                    except Exception:
                        local_state = {}
                    for t in tasks:
                        if t["ant_id"] in local_state:
                            t["ant_active"] = local_state[t["ant_id"]]
                    # 只顯示待認領（0）和標注中（1），已完成（2）不在此列
                    tasks = [t for t in tasks if t.get("ant_active", 0) != 2]
                    st.session_state["m026_tasks"] = tasks
                    st.session_state["m026_tasks_tid"] = tenant_id
                    st.session_state.pop("m026_task_err", None)
                except Exception as exc:
                    st.session_state["m026_task_err"] = str(exc)
                    st.session_state.pop("m026_tasks", None)

    if "m026_task_err" in st.session_state:
        st.error(f"❌ {st.session_state.pop('m026_task_err')}")

    if "m026_claim_result" in st.session_state:
        r = st.session_state.pop("m026_claim_result")
        if r.get("ok"):
            st.success("✅ 任務已認領！請點「執行」載入圖片，再切換到「標注工作台」開始標注。")
        else:
            st.error(f"❌ {r['error']}")

    tasks: list[dict] = st.session_state.get("m026_tasks", [])
    selected_ant_id = st.session_state.get("m026_selected_ant_id", "")

    if tasks:
        st.divider()
        st.subheader(f"任務清單（{len(tasks)} 筆）")
        PAGE_SIZE = 50
        page = st.session_state.get("m026_page", 0)
        n_pages = max(1, (len(tasks) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, n_pages - 1)

        if n_pages > 1:
            c1, c2, c3 = st.columns([1, 3, 1])
            with c1:
                if st.button("← 上一頁", disabled=page == 0, key="m026_prev"):
                    st.session_state["m026_page"] = page - 1; st.rerun()
            with c2:
                st.caption(f"第 {page+1}/{n_pages} 頁")
            with c3:
                if st.button("下一頁 →", disabled=page == n_pages-1, key="m026_next"):
                    st.session_state["m026_page"] = page + 1; st.rerun()

        pending_count = sum(1 for t in tasks if t.get("ant_active", 0) == 0)
        if pending_count == 0:
            in_progress = sum(1 for t in tasks if t.get("ant_active", 0) == 1)
            if in_progress:
                st.info(f"目前無新任務可認領。有 {in_progress} 個任務標注中，可點「繼續」接續作業。")
            else:
                st.info("目前無可處理的任務。")

        for idx, task in enumerate(tasks[page*PAGE_SIZE:(page+1)*PAGE_SIZE]):
            ant_id     = task["ant_id"]
            ant_active = task.get("ant_active", 0)
            icon       = _ANT_ACTIVE_ICON.get(ant_active, "⚪")
            label      = _ANT_ACTIVE_LABEL.get(ant_active, str(ant_active))
            ctx        = _format_context(task.get("external_context", {}))

            c_info, c_btn = st.columns([4, 1])
            with c_info:
                is_selected = ant_id == selected_ant_id
                st.markdown(
                    f"{'🔵 ' if is_selected else ''}{icon} **{ant_id}** — {label}"
                    + (f"　`{ctx}`" if ctx else "")
                )
            with c_btn:
                if ant_active == 0:
                    if st.button("✋ 選取", key=f"m026_sel_{page}_{idx}"):
                        st.session_state["m026_selected_ant_id"] = ant_id
                        st.rerun()
                elif ant_active == 1:
                    if st.button("🔄 繼續", key=f"m026_sel_{page}_{idx}",
                                 help="此任務已認領，點此繼續標注"):
                        st.session_state["m026_selected_ant_id"] = ant_id
                        st.rerun()
            st.markdown("---")

    if not selected_ant_id:
        if tasks:
            st.warning("⬆️ 請先點選任務清單中的「選取」或「繼續」按鈕，再按「執行」。")
        else:
            st.warning("⬆️ 請先點選「查看任務清單」，再選取任務後按「執行」。")
        return {"mode": "iwsc", "tenant_id": tenant_id, "user_id": user_id, "ant_id": ""}

    st.success(f"✅ 已選取：**{selected_ant_id}**　確認後按「執行」載入圖片。")
    return {
        "mode": "iwsc",
        "tenant_id": tenant_id,
        "user_id": user_id.strip(),
        "ant_id": selected_ant_id,
    }


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def render_input() -> dict:
    _ui.inject_streamlit_zh_overrides()
    st.title("📥 資料來源")
    st.caption("選擇資料來源，建立標準化圖片清單（DatasetManifest）供後續標注使用。")

    cfg = _cfg.load_config()

    MODE_OPTIONS = ["📁 本地資料夾", "🔌 外部任務系統"]
    MODE_MAP     = {"📁 本地資料夾": "local", "🔌 外部任務系統": "iwsc"}
    MODE_LABEL   = {"local": "📁 本地資料夾", "iwsc": "🔌 外部任務系統"}

    default_label = MODE_LABEL.get(cfg.get("last_mode", "local"), "📁 本地資料夾")
    sel_label = st.radio("來源類型", MODE_OPTIONS,
                         index=MODE_OPTIONS.index(default_label),
                         horizontal=True, key="m026_mode")
    mode = MODE_MAP[sel_label]

    cfg["last_mode"] = mode
    _cfg.save_config(cfg)

    st.divider()

    if mode == "local":
        return _render_local(cfg)
    elif mode == "remote":
        return _render_remote(cfg)
    else:
        return _render_iwsc()
