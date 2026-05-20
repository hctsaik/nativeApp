from __future__ import annotations

import importlib.util as _ilu
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
    st.caption("依分類標籤將圖片與標注 JSON 複製到指定輸出目錄的子資料夾。")

    db_path = _cfg.get_manifest_db_path()
    manifests = _mdb.list_manifests(db_path)

    if not manifests:
        st.warning(
            "尚未建立任何 Manifest，請先執行 **010 - Data Feeder** 選取圖片資料夾。"
        )
        return {
            "manifest_id": "",
            "export_dir": "",
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

    # ── 1. 整理圖片輸出資料夾（C）────────────────────────────────────────────
    st.subheader("1. 整理圖片輸出目錄")
    st.caption("有分類標籤的圖片會依「輸出目錄/分類名稱/」結構複製，原始檔案不受影響。")

    default_export = str(_cfg.get_default_export_dir(manifest_id))

    export_dir = st.text_input(
        "圖片整理輸出目錄",
        value=st.session_state.get("m013_export_dir_" + manifest_id, default_export),
        key="m013_export_dir_" + manifest_id,
        placeholder="例：C:/Users/user/export",
        help="有分類的圖片與同名 .json 會複製到此目錄的子資料夾。預設為 CIM log 目錄下的 exports/。",
    )
    if export_dir:
        st.info(f"輸出範例：`{export_dir}/分類A/frame_000001.jpg`")

    st.divider()

    # ── 2. 更新選項 ───────────────────────────────────────────────────────────
    st.subheader("2. 執行選項")

    cfg = _cfg.load_config()

    organize_images = st.checkbox(
        "依分類整理圖片並帶走標注 JSON",
        value=cfg.get("organize_images", True),
        key="m013_organize_images",
        help="圖片與同名 .json 一起複製到「輸出目錄/分類名稱/」。原始檔案不受影響，衝突時以新檔覆蓋。",
    )
    if not organize_images:
        st.caption("停用後不會複製任何檔案。")

    # 儲存選項到 config（下次自動恢復）
    try:
        cfg["organize_images"] = organize_images
        _cfg.save_config(cfg)
    except Exception:
        pass

    return {
        "manifest_id": manifest_id,
        "export_dir": export_dir,
        "organize_images": organize_images,
        "dry_run": True,
    }
