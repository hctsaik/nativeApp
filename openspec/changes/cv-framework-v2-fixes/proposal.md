# 變更：CV 框架 v2 修補（cv-framework-v2-fixes）

## 為何需要此變更

CV 框架 v2 實作完成後，發現 4 個影響正確性或完整性的缺口：

### Fix 1 — 雙 Pane 問題（workflow / management 工具）

`engine.py` 永遠同時啟動 input + output 兩個 Streamlit 程序。
`workflow_runner.py` / `management_runner.py` 沒有 split 檔，因此兩個 pane 都執行同一個完整 UI：
- 資源浪費（兩倍程序）
- Portal 使用者看到兩份一樣的畫面

### Fix 2 — `publish()` 未納入 `plugin.yaml`

`publish()` 只抓 `*.py`，不包含 `plugin.yaml`。
Prod 模式（`CIM_DEV_MODE=0`）從 DB snapshot 載入時：
- `_plugin_from_db()` 找不到 plugin.yaml，回傳 `version="unknown"`
- 名稱只靠 `plugins` 表靜態值，與快照內容脫鉤

### Fix 3 — Prod 模式 Workflow 沒有 DB 路徑

`list_workflows()` 在 prod 模式查詢 `workflows` 表，但這張表從未被寫入。
`CIM_DEV_MODE=0` 時，所有 workflow 直接消失。
需要 `sync_workflows()` 方法將 filesystem 的 `workflow.yaml` 同步到 DB。

### Fix 4 — `AuthProvider` 從未實際被呼叫

`auth_provider.py` 已完整實作並測試，但 `cv_framework_runner.py` 和 `workflow_runner.py`
執行前都沒有 `check_permission()`。Permission 設定存在 DB 裡但形同虛設。

## 變更目標

- 修補上述 4 個缺口，不引入新功能
- 保持所有現有測試通過
- 每個 fix 附帶對應單元測試

## 不納入

- Portal UI 的 category 分組顯示（另立 spec）
- Prod 模式 plugin 整合端到端測試（複雜度高，另立 spec）
- 實際 web service 帳號整合
