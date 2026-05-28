from __future__ import annotations

import importlib.util as _ilu
import io
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_026_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location("_manifest_db", _HERE.parent / "shared" / "_manifest_db.py")
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_SOURCE_ICON = {"local": "📁", "iwsc": "🔌"}
_SOURCE_NAME = {"local": "本地資料夾", "iwsc": "外部任務系統"}

_THUMB_COLS = 5  # 每行顯示幾張縮圖


@st.cache_data(show_spinner=False, max_entries=200)
def _thumb(file_path: str) -> bytes | None:
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(file_path)).convert("RGB")
        img.thumbnail((160, 120), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()
    except Exception:
        return None


def _render_thumb_grid(items: list[dict]) -> None:
    """以 Grid 方式顯示縮圖，每列 _THUMB_COLS 張。"""
    cols = st.columns(_THUMB_COLS)
    for i, item in enumerate(items):
        fp = item.get("file_path", "")
        fname = Path(fp).name if fp else ""
        with cols[i % _THUMB_COLS]:
            thumb = _thumb(fp) if fp else None
            if thumb:
                st.image(thumb, caption=fname, width=140)
            else:
                st.caption(f"⚠️ {fname}")


def _render_status(manifest_id: str, source_type: str, shared: dict, manifest: dict | None) -> None:
    if not manifest:
        return
    icon = _SOURCE_ICON.get(source_type, "📦")
    name = _SOURCE_NAME.get(source_type, source_type)
    st.success(
        f"{icon} **{manifest['name']}**　共 {manifest.get('item_count', 0)} 張圖片\n\n"
        f"來源：{name}"
    )
    if source_type == "iwsc":
        ant_id  = shared.get("iwsc_ant_id", "")
        task_id = shared.get("iwsc_task_id", "")
        if ant_id:
            st.info(f"🔌 外部任務：**{ant_id}**　`task_id: {task_id[:12]}…`")


def render_output(result: dict) -> None:
    mode = result.get("mode", "idle")

    if mode == "error":
        st.error(f"❌ {result.get('error', '未知錯誤')}")
        return

    if mode == "idle":
        shared      = _cfg.read_shared()
        manifest_id = shared.get("last_manifest_id", "")
        source_type = shared.get("source_type", "local")
        if not manifest_id:
            st.info("尚未載入資料。請在左側設定來源後按「執行」。")
            return
        db_path   = _cfg.get_manifest_db_path()
        manifests = _mdb.list_manifests(db_path)
        manifest  = next((m for m in manifests if m["manifest_id"] == manifest_id), None)
        _render_status(manifest_id, source_type, shared, manifest)
        if manifest:
            items = _mdb.get_manifest_items(db_path, manifest_id, limit=20)
            if items:
                st.divider()
                st.caption(f"預覽前 {len(items)} 張（共 {manifest.get('item_count', 0)} 張）")
                _render_thumb_grid(items)
        return

    if mode == "ready":
        manifest_id   = result.get("manifest_id", "")
        manifest_name = result.get("manifest_name", "")
        total         = result.get("total_count", 0)
        items         = result.get("items", [])
        source_type   = _cfg.read_shared().get("source_type", "local")

        icon = _SOURCE_ICON.get(source_type, "📦")
        name = _SOURCE_NAME.get(source_type, source_type)

        st.success(
            f"{icon} **{manifest_name}** 已載入！　來源：{name}　共 **{total}** 張圖片\n\n"
            "✅ 請切換到「**✏️ 標注工作台**」開始標注。"
        )

        if result.get("iwsc_ant_id"):
            st.info(f"🔌 已認領外部任務：**{result['iwsc_ant_id']}**")

        if items:
            st.divider()
            st.caption(f"預覽前 {len(items)} 張（共 {total} 張）")
            _render_thumb_grid(items)
