from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

import streamlit as st

# ─── 動態載入 _config + _manifest_db ─────────────────────────────────────────

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_013_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def render_input() -> dict:
    st.subheader("📁 Update — 結果更新")
    st.caption(
        "將 module_012 的標注（X-AnyLabeling JSON）與分類結果整理成摘要 JSON，"
        "並可選擇複製回原始資料夾，或依分類標籤整理圖片到子資料夾。"
        "執行後請切換至 Output 頁面預覽並確認。"
    )

    db_path = _cfg.get_manifest_db_path()
    manifests = _mdb.list_manifests(db_path)

    if not manifests:
        st.warning(
            "尚未建立任何 Manifest，請先執行 **010 - Data Feeder** 選取圖片資料夾。"
        )
        return {
            "manifest_id": "",
            "dest_folder": "",
            "copy_annotations": True,
            "organize_images": True,
            "dry_run": True,
        }

    # ── 自動銜接最後一個 manifest（從 shared.json 讀取） ──────────────────────
    shared_id = _cfg.get_shared_manifest_id()
    manifests_list = list(manifests)
    selected = next(
        (m for m in manifests_list if m["manifest_id"] == shared_id),
        manifests_list[0],
    )
    manifest_id = selected["manifest_id"]

    st.info(
        f"📦 **{selected['name']}**　{selected.get('item_count', 0)} 張　"
        f"　｜　若要切換請回 Data Feeder 重新執行"
    )

    st.divider()

    # ── 1. 標注輸出位置（自動）────────────────────────────────────────────────
    st.subheader("1. 標注輸出位置")
    st.info("✅ 標注 JSON 將直接存回**影像所在的同一目錄**（與影像同名，例：`image_001.json`）。")

    st.divider()

    # ── 2. 整理圖片輸出資料夾（C）────────────────────────────────────────────
    st.subheader("2. 整理圖片輸出資料夾（C）")
    st.caption(
        "分類後的圖片會複製到此資料夾的 `{分類名稱}/` 子目錄。"
        "**請務必設為原始圖片資料夾以外的位置**，避免重複掃描造成資料增殖。"
    )

    # 預設：workspace 內的 export/ 目錄（完全在 source 資料夾之外）
    ws_dir = _cfg.get_workspace_dir_for_manifest(manifest_id)
    default_export = str(ws_dir / "export")

    export_dir = st.text_input(
        "圖片整理輸出目錄",
        value=st.session_state.get("m013_export_dir_" + manifest_id, default_export),
        key="m013_export_dir_" + manifest_id,
        placeholder="例：C:/Users/user/export",
        help="分類圖片輸出到此目錄的子資料夾，與原始圖片分開，不影響下次 Data Feeder 掃描。",
    )
    if export_dir:
        st.info(f"輸出範例：`{export_dir}/分類A/frame_000001.jpg`")

    st.divider()

    # ── 3. 更新選項 ───────────────────────────────────────────────────────────
    st.subheader("3. 更新選項")

    cfg = _cfg.load_config()

    copy_annotations = st.checkbox(
        "B｜確認標注 JSON 已存回影像所在目錄（與影像同名）",
        value=cfg.get("copy_annotations", True),
        key="m013_copy_annotations",
        help="X-AnyLabeling 已將標注存在影像同目錄（例：image_001.jpg → image_001.json）。此選項確認並統計已存在的標注檔。",
    )

    organize_images = st.checkbox(
        "C｜依分類標籤將圖片複製到整理輸出目錄的子資料夾",
        value=cfg.get("organize_images", True),
        key="m013_organize_images",
        help="圖片複製到「整理輸出目錄/分類名稱/」。原始圖片不會被刪除。",
    )

    st.caption("⚠️ 以上操作均為「複製」，原始檔案不會被刪除或移動。衝突時以新檔案覆蓋。")

    st.divider()

    # ── 4. 外部 DB 更新（placeholder）────────────────────────────────────────
    st.subheader("4. 外部 DB 更新")
    st.info("🔧 外部 DB 更新功能開發中", icon="🔧")

    # 儲存選項到 config（下次自動恢復）
    try:
        cfg["copy_annotations"] = copy_annotations
        cfg["organize_images"] = organize_images
        _cfg.save_config(cfg)
    except Exception:
        pass

    return {
        "manifest_id": manifest_id,
        "dest_folder": "",  # 不再使用；B 操作直接寫回影像同目錄
        "export_dir": export_dir,
        "copy_annotations": copy_annotations,
        "organize_images": organize_images,
        "dry_run": True,
    }
