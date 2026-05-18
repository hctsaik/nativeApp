"""
Pipeline Sheet — 線性步驟式標注工作流
DataFeeder → Module 006 標注 → Result Sink 匯出
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import os
import uuid
from pathlib import Path

import streamlit as st

# ── 路徑計算 ──────────────────────────────────────────────────────────────────
# sheets/ → scripts/ → python-engine/ → sidecar/ → nativeApp/
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR = Path(os.environ.get(
    "CIM_LOG_DIR",
    str(_PROJECT_ROOT / "tmp" / "cim_log"),
))
_MANIFEST_DB_PATH = _CIM_LOG_DIR / "db" / "manifest.sqlite"
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


# ── 動態載入工具函式 ───────────────────────────────────────────────────────────

def _load_manifest_db():
    """載入 shared/_manifest_db.py，失敗時回傳 None。"""
    try:
        _spec = _ilu.spec_from_file_location(
            "_manifest_db",
            _SCRIPTS_DIR / "shared" / "_manifest_db.py",
        )
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        return _mod
    except Exception:
        return None


def _load_process(module_dir: str, file_name: str):
    """動態載入指定模組的 process 檔案，失敗時回傳 None。"""
    try:
        _path = _SCRIPTS_DIR / module_dir / file_name
        _spec = _ilu.spec_from_file_location(module_dir, _path)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        return _mod
    except Exception:
        return None


# ── Session state 初始化 ───────────────────────────────────────────────────────

def _init_state():
    st.session_state.setdefault("pl_step", 1)
    st.session_state.setdefault("pl_manifest_id", None)
    st.session_state.setdefault("pl_manifest_name", "")
    st.session_state.setdefault("pl_manifest_item_count", 0)
    st.session_state.setdefault("pl_run_id", None)
    st.session_state.setdefault("pl_name", "")
    st.session_state.setdefault("pl_history", [])


def _reset_pipeline():
    for key in ["pl_step", "pl_manifest_id", "pl_manifest_name",
                "pl_manifest_item_count", "pl_run_id", "pl_name"]:
        if key in st.session_state:
            del st.session_state[key]
    _init_state()


# ── 步驟進度列 ─────────────────────────────────────────────────────────────────

def _render_step_bar(current_step: int):
    steps = ["① 資料來源", "② 標注", "③ 匯出"]
    icons = ["📁", "🏷️", "💾"]
    cols = st.columns(3)
    for i, (col, step, icon) in enumerate(zip(cols, steps, icons)):
        with col:
            step_num = i + 1
            if step_num < current_step:
                st.success(f"{icon} {step} ✅")
            elif step_num == current_step:
                st.info(f"{icon} {step} ⏳ 進行中")
            else:
                st.caption(f"{icon} {step} ⬜")


# ── Step 1：資料來源 ───────────────────────────────────────────────────────────

def _render_step1():
    st.markdown("### 📁 步驟 1：選擇資料來源")

    pl_name = st.text_input(
        "Pipeline 名稱",
        value=st.session_state.get("pl_name", ""),
        placeholder="例如：貓狗分類標注批次 2026-05",
        key="pl_name_input",
    )
    st.session_state["pl_name"] = pl_name

    tab_exist, tab_scan = st.tabs(["📋 選擇現有 Manifest", "📁 快速掃描資料夾"])

    selected_manifest_id = None
    selected_manifest_name = ""
    selected_item_count = 0

    _mdb = _load_manifest_db()

    with tab_exist:
        if _mdb is None:
            st.warning("shared/_manifest_db.py 尚未安裝，無法讀取 Manifest。")
        elif not _MANIFEST_DB_PATH.exists():
            st.info("Manifest 資料庫尚未建立，請先使用 Module 010 Data Feeder 建立資料來源。")
        else:
            try:
                manifests = _mdb.list_manifests(_MANIFEST_DB_PATH)
                if not manifests:
                    st.info("尚無 Manifest。請先在 Module 010 Data Feeder 建立資料來源。")
                else:
                    opts = ["（請選擇）"] + [
                        f"{m['name']}（{m['item_count']} 筆）" for m in manifests
                    ]
                    sel = st.selectbox("選擇 Manifest", opts, key="pl_manifest_sel")
                    if sel != opts[0]:
                        idx = opts.index(sel) - 1
                        selected_manifest_id = manifests[idx]["manifest_id"]
                        selected_manifest_name = manifests[idx]["name"]
                        selected_item_count = manifests[idx]["item_count"]
                        st.success(
                            f"已選取：**{selected_manifest_name}**，共 {selected_item_count} 筆圖片"
                        )
            except Exception as e:
                st.error(f"讀取 Manifest 失敗：{e}")

    with tab_scan:
        st.caption("掃描指定資料夾，自動建立新的 Manifest 並存入資料庫。")
        scan_dir = st.text_input("資料夾路徑", placeholder="/path/to/images", key="pl_scan_dir")
        scan_name = st.text_input(
            "Manifest 名稱",
            value="新資料集",
            key="pl_scan_name",
        )
        scan_recursive = st.checkbox("遞迴掃描子資料夾", value=True, key="pl_scan_recursive")

        if st.button("🔍 掃描並建立 Manifest", key="pl_btn_scan"):
            if not scan_dir or not Path(scan_dir).exists():
                st.error("請輸入有效的資料夾路徑。")
            else:
                proc010 = _load_process("module_010", "010_process.py")
                if proc010 is None:
                    st.error("Module 010 尚未安裝（找不到 010_process.py）。")
                else:
                    with st.spinner("掃描中…"):
                        try:
                            result = proc010.execute_logic({
                                "source_type": "folder",
                                "folder_path": scan_dir,
                                "manifest_name": scan_name,
                                "recursive": scan_recursive,
                            })
                            if result.get("ok"):
                                selected_manifest_id = result["manifest_id"]
                                selected_manifest_name = result.get("manifest_name", scan_name)
                                selected_item_count = result.get("item_count", 0)
                                st.success(
                                    f"掃描完成！建立 Manifest **{selected_manifest_name}**，"
                                    f"共 {selected_item_count} 筆圖片。"
                                )
                                st.session_state["pl_manifest_id"] = selected_manifest_id
                                st.session_state["pl_manifest_name"] = selected_manifest_name
                                st.session_state["pl_manifest_item_count"] = selected_item_count
                            else:
                                st.error(f"掃描失敗：{result.get('error', '未知錯誤')}")
                        except Exception as e:
                            st.error(f"執行失敗：{e}")

    st.divider()
    col_next, _ = st.columns([1, 3])
    with col_next:
        _use_id = selected_manifest_id or st.session_state.get("pl_manifest_id")
        btn_label = "下一步 →" if _use_id else "請先選擇資料來源"
        if st.button(btn_label, key="pl_btn_step1_next", disabled=not bool(_use_id)):
            if selected_manifest_id:
                st.session_state["pl_manifest_id"] = selected_manifest_id
                st.session_state["pl_manifest_name"] = selected_manifest_name
                st.session_state["pl_manifest_item_count"] = selected_item_count
            st.session_state["pl_step"] = 2
            st.rerun()


# ── Step 2：標注 ───────────────────────────────────────────────────────────────

def _render_step2():
    st.markdown("### 🏷️ 步驟 2：使用 Module 006 進行標注")

    manifest_name = st.session_state.get("pl_manifest_name", "（未選取）")
    item_count = st.session_state.get("pl_manifest_item_count", 0)
    manifest_id = st.session_state.get("pl_manifest_id", "")

    st.info(
        f"**已選取 Manifest：** {manifest_name}　｜　**圖片數量：** {item_count} 筆"
    )

    st.markdown("#### 操作說明")
    st.markdown(
        f"""
請切換到 **Module 006（動物影像標注專案）** 頁面，依照以下步驟進行標注：

1. 在頁面頂端展開 **「📦 使用 Data Feeder Manifest（選填）」** 區塊
2. 在下拉選單中選取 **「{manifest_name}」**
3. 完成標注設定後，點擊「準備標注專案」並啟動 X-AnyLabeling
4. 完成所有圖片標注後，回到此頁點擊下方「✅ 標注已完成」按鈕

> **Manifest ID（供進階使用）：** `{manifest_id}`
        """
    )

    st.divider()
    col_prev, col_next, _ = st.columns([1, 2, 3])
    with col_prev:
        if st.button("← 上一步", key="pl_btn_step2_prev"):
            st.session_state["pl_step"] = 1
            st.rerun()
    with col_next:
        if st.button("✅ 標注已完成，進入下一步", key="pl_btn_step2_next"):
            st.session_state["pl_step"] = 3
            st.session_state["pl_run_id"] = uuid.uuid4().hex
            st.rerun()


# ── Step 3：匯出 ───────────────────────────────────────────────────────────────

def _render_step3():
    st.markdown("### 💾 步驟 3：匯出標注結果")

    manifest_name = st.session_state.get("pl_manifest_name", "（未選取）")
    item_count = st.session_state.get("pl_manifest_item_count", 0)
    run_id = st.session_state.get("pl_run_id") or uuid.uuid4().hex
    st.session_state["pl_run_id"] = run_id

    st.info(
        f"**Manifest：** {manifest_name}　｜　**圖片數量：** {item_count} 筆"
    )

    st.markdown("**Run ID**")
    st.code(run_id, language=None)

    st.markdown("#### 匯出設定")
    col_fmt, col_dir = st.columns(2)
    with col_fmt:
        export_formats = st.multiselect(
            "匯出格式",
            options=["coco", "yolo-detection", "csv"],
            default=["coco", "yolo-detection"],
            key="pl_export_formats",
        )
    with col_dir:
        default_export_dir = str(_PROJECT_ROOT / "tmp" / "pipeline_exports" / run_id[:8])
        export_dir = st.text_input(
            "匯出目錄",
            value=default_export_dir,
            key="pl_export_dir",
        )

    st.markdown("#### 資料集分割比例")
    col_train, col_val, col_test = st.columns(3)
    with col_train:
        split_train = st.number_input("訓練集 (%)", min_value=0, max_value=100, value=70, step=5, key="pl_split_train")
    with col_val:
        split_val = st.number_input("驗證集 (%)", min_value=0, max_value=100, value=15, step=5, key="pl_split_val")
    with col_test:
        split_test = st.number_input("測試集 (%)", min_value=0, max_value=100, value=15, step=5, key="pl_split_test")

    split_sum = split_train + split_val + split_test
    if split_sum != 100:
        st.warning(f"分割比例總和為 {split_sum}%，建議調整為 100%。")

    st.divider()
    col_prev, col_exec, _ = st.columns([1, 2, 3])
    with col_prev:
        if st.button("← 上一步", key="pl_btn_step3_prev"):
            st.session_state["pl_step"] = 2
            st.rerun()
    with col_exec:
        if st.button("💾 執行匯出", key="pl_btn_export", type="primary"):
            if not export_formats:
                st.error("請至少選擇一種匯出格式。")
            else:
                proc011 = _load_process("module_011", "011_process.py")
                if proc011 is None:
                    st.error("Module 011 尚未安裝（找不到 011_process.py）。")
                else:
                    with st.spinner("匯出中…"):
                        try:
                            result = proc011.execute_logic({
                                "manifest_id": st.session_state.get("pl_manifest_id"),
                                "run_id": run_id,
                                "export_formats": export_formats,
                                "export_dir": export_dir,
                                "split": {
                                    "train": split_train / 100,
                                    "val": split_val / 100,
                                    "test": split_test / 100,
                                },
                            })

                            if result.get("ok"):
                                st.success("✅ 匯出成功！")
                                export_paths = result.get("export_paths", {})
                                if export_paths:
                                    st.markdown("**匯出路徑：**")
                                    for fmt, path in export_paths.items():
                                        st.code(f"[{fmt}] {path}", language=None)

                                # 記錄到歷史
                                history_entry = {
                                    "run_id": run_id,
                                    "pipeline_name": st.session_state.get("pl_name", "（未命名）"),
                                    "manifest_name": manifest_name,
                                    "item_count": item_count,
                                    "export_formats": export_formats,
                                    "export_dir": export_dir,
                                    "export_paths": export_paths,
                                }
                                st.session_state["pl_history"].append(history_entry)

                                st.markdown("---")
                                if st.button("🔄 開始新 Pipeline", key="pl_btn_new"):
                                    _reset_pipeline()
                                    st.rerun()
                            else:
                                st.error(f"匯出失敗：{result.get('error', '未知錯誤')}")
                        except Exception as e:
                            st.error(f"執行失敗：{e}")


# ── 執行歷史 ───────────────────────────────────────────────────────────────────

def _render_history():
    history = st.session_state.get("pl_history", [])
    if not history:
        return

    with st.expander(f"📜 Pipeline 執行歷史（{len(history)} 筆）", expanded=False):
        for i, entry in enumerate(reversed(history), 1):
            st.markdown(
                f"**#{i}** `{entry.get('run_id', '')[:8]}…`　"
                f"**{entry.get('pipeline_name', '（未命名）')}**　—　"
                f"{entry.get('manifest_name', '')}（{entry.get('item_count', 0)} 筆）　"
                f"格式：{', '.join(entry.get('export_formats', []))}"
            )
            paths = entry.get("export_paths", {})
            if paths:
                for fmt, path in paths.items():
                    st.caption(f"　　[{fmt}] {path}")
            if i < len(history):
                st.divider()


# ── 主入口 ─────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Pipeline Sheet", layout="wide")
    st.markdown("## 🔗 Pipeline Sheet — 自訂標注工作流")

    _init_state()

    current_step = st.session_state.get("pl_step", 1)
    _render_step_bar(current_step)
    st.divider()

    if current_step == 1:
        _render_step1()
    elif current_step == 2:
        _render_step2()
    elif current_step == 3:
        _render_step3()

    _render_history()


if __name__ == "__main__":
    main()
