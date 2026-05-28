"""Shared UI helpers for CV module input / output pages.

Import pattern (use when sys.path doesn't include scripts/):
    import importlib.util
    from pathlib import Path
    _spec = importlib.util.spec_from_file_location(
        "ui_components",
        Path(__file__).resolve().parent.parent / "shared" / "ui_components.py"
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
"""
from __future__ import annotations

import calendar
from datetime import date

import streamlit as st


# ── Date helpers ─────────────────────────────────────────────────────────────

def three_months_ago(ref: date | None = None) -> date:
    """Return the date exactly 3 calendar months before *ref* (default: today)."""
    ref = ref or date.today()
    month = ref.month - 3
    year  = ref.year
    if month <= 0:
        month += 12
        year  -= 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(ref.day, max_day))


def date_input_single(
    label: str = "選擇日期",
    default: date | None = None,
    key: str = "date_single",
) -> date:
    """Standard single-date picker. Default is today."""
    return st.date_input(label, value=default or date.today(), key=key)


def date_input_range(
    key_from: str = "date_from",
    key_to:   str = "date_to",
    default_from: date | None = None,
    default_to:   date | None = None,
) -> tuple[date, date]:
    """Standard From / To date range picker.

    Default range: 3 months ago → today.
    Shows a warning when From > To.
    Returns (date_from, date_to).
    """
    today = date.today()
    d_from = default_from or three_months_ago(today)
    d_to   = default_to   or today

    col_from, col_to = st.columns(2)
    with col_from:
        date_from = st.date_input("From", value=d_from, key=key_from)
    with col_to:
        date_to = st.date_input("To", value=d_to, key=key_to)

    if date_from > date_to:
        st.warning("From 日期不能晚於 To 日期。")

    return date_from, date_to


# ── Input widgets ─────────────────────────────────────────────────────────────

def parts_input(key: str = "parts_input", placeholder: str = "輸入 Parts 編號或說明") -> str:
    """Standard Parts-number input rendered as label + text field on one row."""
    col_label, col_field = st.columns([1, 4])
    with col_label:
        st.markdown("**Parts**")
    with col_field:
        return st.text_input(
            "parts_hidden",
            label_visibility="collapsed",
            placeholder=placeholder,
            key=key,
        )


# ── Feedback / notifications ──────────────────────────────────────────────────

def save_success_toast(message: str = "儲存成功！") -> None:
    """Non-intrusive success toast — use instead of st.success() after DB save."""
    st.toast(message, icon=":material/check_circle:")


def save_error_toast(message: str = "儲存失敗") -> None:
    """Non-intrusive error toast."""
    st.toast(message, icon=":material/error:")


# ── Download ──────────────────────────────────────────────────────────────────

def download_image_button(
    image_bytes: bytes,
    filename: str = "image.png",
    label: str = "下載",
    key: str = "dl_btn",
) -> None:
    """Standard image download button."""
    st.download_button(
        label=label,
        data=image_bytes,
        file_name=filename,
        mime="image/png",
        icon=":material/image:",
        key=key,
    )


def inject_streamlit_zh_overrides() -> None:
    """Inject JS to replace Streamlit's hardcoded English error dialogs with Chinese.

    Call once at the top of any render_input() / render_output() function.
    Handles the "Connection error" / "server is not responding" dialog.
    """
    st.markdown(
        """
<script>
(function patchStreamlitDialogs() {
  const REPLACEMENTS = [
    ["Connection error", "連線中斷"],
    ["Streamlit server is not responding. Are you connected to the internet?",
     "與伺服器的連線已中斷，請點擊右上角 ✕ 關閉後重新整理頁面。"],
    ["Are you connected to the internet?", "請重新整理頁面以恢復連線。"],
  ];
  function replaceText(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      for (const [en, zh] of REPLACEMENTS) {
        if (node.nodeValue && node.nodeValue.includes(en)) {
          node.nodeValue = node.nodeValue.replace(en, zh);
        }
      }
    }
  }
  const obs = new MutationObserver((muts) => {
    for (const m of muts) {
      for (const n of m.addedNodes) {
        if (n.nodeType === 1) replaceText(n);
      }
    }
  });
  obs.observe(document.body, { childList: true, subtree: true });
  replaceText(document.body);
})();
</script>
""",
        unsafe_allow_html=True,
    )
