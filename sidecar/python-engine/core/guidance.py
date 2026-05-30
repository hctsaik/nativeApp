"""Turn raw operational errors into actionable, operator-facing guidance.

Operators on the data-source / external-task pages used to see a bare error
string (e.g. a `ConnectionRefusedError` repr) and had to dig through engine.log.
`diagnose()` matches common failure signatures and returns a structured card —
a one-line cause plus concrete next steps — so the fix is self-service.

Pure / dependency-free so it is unit-testable and safe to import anywhere.
"""

from __future__ import annotations

import re

# (compiled regex, builder) — first match wins. Builders return the card dict.
_RULES: list[tuple[re.Pattern, dict]] = [
    (re.compile(r"10061|connection refused|max retries|failed to establish|"
                r"connectionrefusederror|connection aborted|name or service not known|"
                r"getaddrinfo failed|連不上|無法連線", re.I),
     {"title": "外部系統連不上",
      "hint": "目標 server 沒有回應，多半是 server 未啟動或 host 填錯。",
      "steps": ["確認外部任務系統（如 iWISC sample server，port 8765）已啟動",
                "到管理中心 → External 用「🔌 測試連線」確認 host 可達",
                "檢查 server host 是否含正確的 http://、port 與路徑"]}),
    (re.compile(r"\b401\b|unauthorized|forbidden|\b403\b|invalid token|"
                r"authentication|授權|憑證", re.I),
     {"title": "認證失敗（token 無效或未設定）",
      "hint": "server 拒絕了請求，通常是 API token 未設或已過期。",
      "steps": ["確認註冊時填的 token 環境變數（api_token_env）已在環境中設定值",
                "向外部系統管理者確認 token 仍有效、權限足夠",
                "重設環境變數後重啟 app，再重新執行"]}),
    (re.compile(r"no tenant|tenant not (found|configured)|empty tenant|"
                r"沒有.*租戶|尚未.*tenant|未設定.*tenant|找不到.*租戶|無可用的外部系統", re.I),
     {"title": "尚未設定外部任務系統（Tenant）",
      "hint": "還沒有任何已註冊的外部系統可供認領任務。",
      "steps": ["到管理中心 → External 新增外部系統（填名稱 / host / 格式）",
                "或編輯 config/external_systems.yaml 宣告後重新載入",
                "確認該系統已指派給目前使用者"]}),
    (re.compile(r"已被.*認領|already claimed|task.*conflict|conflicterror|"
                r"unique constraint.*tenant|integrityerror.*ant", re.I),
     {"title": "任務已被認領",
      "hint": "這張任務已被其他人或另一個程序先認領了。",
      "steps": ["重新整理任務清單，挑選其他「待認領」的任務",
                "若確認是自己稍早認領的，請直接到「標注工作台」繼續"]}),
    (re.compile(r"timeout|timed out|逾時|超時", re.I),
     {"title": "連線逾時",
      "hint": "server 有設定但回應太慢或網路不通。",
      "steps": ["確認網路可達外部 server", "稍後重試；若持續，請外部系統管理者檢查負載"]}),
]


def diagnose(error_text: str | None) -> dict | None:
    """Return {title, hint, steps:[...]} for a recognised failure, else None."""
    if not error_text:
        return None
    for pattern, card in _RULES:
        if pattern.search(str(error_text)):
            return card
    return None


def render(error_text: str | None, st) -> bool:
    """Render an actionable card into a Streamlit container. Returns True if a
    known failure was recognised (caller can skip the raw error then)."""
    card = diagnose(error_text)
    if not card:
        return False
    st.error(f"❌ {card['title']}")
    st.caption(card["hint"])
    st.markdown("**怎麼解決：**\n" + "\n".join(f"- {s}" for s in card["steps"]))
    with st.expander("技術細節（原始錯誤）", expanded=False):
        st.code(str(error_text))
    return True
