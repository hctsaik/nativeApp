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
    # ── Developer / tool-author errors (the self-build debug loop) ────────────
    (re.compile(r"missing cim_sheet_id|missing cim_plugin_id|cim_sheet_id.*cim_plugin_id", re.I),
     {"title": "工具被直接執行（環境變數未由 engine 注入）",
      "hint": "CIM_SHEET_ID / CIM_PLUGIN_ID 由 engine spawn 子程序時注入；單獨跑 runner 不會有。",
      "steps": ["不要直接執行 sheet_runner.py / *_input.py，改用 start-dev.bat 啟動整個 app",
                "catalog（tools.sqlite）會由 plugin.yaml + sheet YAML + config/seed.yaml 首啟自動重建；如懷疑快取髒掉可用 engine --rebuild-catalog 重建"]}),
    (re.compile(r"no folder found for plugin_id|layer file not found|no module folder|"
                r"找不到.*模組|module.*not found", re.I),
     {"title": "找不到模組（尚未註冊或檔名不符）",
      "hint": "engine 靠 plugin.yaml 掃描；檔名須是 <NNN>_process.py / _input.py / _output.py。",
      "steps": ["確認模組資料夾有 plugin.yaml 且 id 正確",
                "確認檔名與短 id 相符（如 module_042 → 042_process.py）",
                "按 portal「重新載入工具」或 POST /reload 重掃（免重啟）"]}),
    (re.compile(r"您沒有.*權限|permission denied|not allowed|沒有執行.*權限|rbac", re.I),
     {"title": "沒有權限（RBAC 擋下）",
      "hint": "目前角色在 config/permissions.yaml 沒有此工具的 view/execute 權限。",
      "steps": ["管理中心 → Permissions 用視覺化矩陣勾選該角色的權限",
                "或 DEV 用上方角色下拉切回 admin 驗證",
                "確認 config/permissions.yaml 已存並重載"]}),
    (re.compile(r"process layer imports streamlit|imports streamlit|streamlit.*process", re.I),
     {"title": "process 層誤用 Streamlit",
      "hint": "*_process.py 必須是純運算（無 Streamlit）；UI 放 *_output.py 或宣告式 output:。",
      "steps": ["把 st.* 呼叫移到 *_output.py / output: 區塊", "process 只回傳 dict 結果"]}),
    (re.compile(r"formschemaerror|outputschemaerror|external_gui.*必須|不支援；可用|需要.*key", re.I),
     {"title": "宣告式 schema 寫錯（form/output/external_gui）",
      "hint": "plugin.yaml 的宣告式區塊欄位有誤，框架已指出原因。",
      "steps": ["依錯誤訊息修正該欄位（type / key / options / args）",
                "參考 scripts/module_007（零-code 範例）的寫法",
                "存檔後按「重新載入工具」重試"]}),
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
