# 設計：CV 框架 v2 修補

---

## Fix 1 — 單 Pane 輸出（workflow / management）

### 問題根因

`engine.py` 的 `ToolProcessManager.start()` 永遠同時啟動兩個 Streamlit 程序：
- input：`CIM_TOOL_LAYER=input`
- output：`CIM_TOOL_LAYER=output`

對 `cv_framework_runner.py` 這樣的雙層工具，兩個 pane 有明確分工。
但 `workflow_runner.py` / `management_runner.py` 是全功能單頁 App，
output pane 只要顯示空白（或提示訊息）即可。

### 解法

在 `workflow_runner.py` 與 `management_runner.py` 的 `main()` 最前面加：

```python
LAYER = os.environ.get("CIM_TOOL_LAYER", "input")
if LAYER == "output":
    st.set_page_config(page_title="…")
    st.info("請在左側頁面操作。")
    st.stop()
```

這樣 output pane 立即停止，不啟動任何邏輯，只佔一個輕量的 Streamlit 程序（幾乎無資源消耗）。

### 測試策略

- 測試框架層面：驗證 source code 中存在 `CIM_TOOL_LAYER` 的判斷
- 邏輯層面：已由 `test_tool_comms.py` 等現有測試覆蓋

---

## Fix 2 — `publish()` 納入 `plugin.yaml`

### 問題根因

```python
# 現有 publish() — 只抓 .py
for py_file in sorted(actual_folder.glob("*.py")):
    content[py_file.name] = py_file.read_text(encoding="utf-8")
```

Prod 模式讀取 snapshot 時，`content_json` 裡沒有 `plugin.yaml`，
導致 `_plugin_from_db()` 無法取得版本、tags、description 等 metadata。

### 解法

```python
# 新 publish() — 同時納入 .py 與 plugin.yaml
for file in sorted(actual_folder.glob("*.py")):
    content[file.name] = file.read_text(encoding="utf-8")
manifest = actual_folder / "plugin.yaml"
if manifest.exists():
    content["plugin.yaml"] = manifest.read_text(encoding="utf-8")
```

`_plugin_from_db()` 也同步更新：從 `content_json["plugin.yaml"]` 讀取完整 metadata，
包含 `name`、`version`、`category`、`description`、`tags`、`runner`。

### 測試策略

| 測試 | 驗證項目 |
|------|---------|
| `test_publish_includes_plugin_yaml` | content_json 含 `plugin.yaml` key |
| `test_plugin_from_db_reads_yaml_version` | prod 模式 get_plugin() 回傳正確 version |
| `test_plugin_from_db_reads_yaml_name` | prod 模式 get_plugin() 回傳正確 name |
| `test_plugin_from_db_fallback_without_yaml` | 無 plugin.yaml snapshot 時不 crash |

---

## Fix 3 — `sync_workflows()` + Prod 模式 Workflow

### 問題根因

Workflow prod 模式需要 `workflows` 和 `workflow_steps` 兩張表有資料，
但目前只有 dev 模式（從 filesystem 讀）能正常運作；沒有機制將 yaml 寫入 DB。

### 解法：新增 `PluginRegistry.sync_workflows()` 方法

```python
def sync_workflows(self) -> list[str]:
    """
    掃描 scripts/workflows/ 下的所有 workflow.yaml，
    寫入（或更新）workflows + workflow_steps 表。
    回傳已同步的 workflow_id 列表。
    """
```

邏輯：
1. 掃描 `WORKFLOWS_DIR`，用 `_load_workflow_yaml()` 解析每個 yaml
2. `INSERT OR REPLACE INTO workflows (...)`
3. 先刪除舊 steps：`DELETE FROM workflow_steps WHERE workflow_id=?`
4. 重新插入所有 steps（依 step_order）
5. 同時確保對應的 plugin 行存在（`INSERT OR IGNORE INTO plugins`）

### Management Center 整合

管理中心「工作流程」Tab 新增「同步 Workflow 到 DB」按鈕，
呼叫 `reg.sync_workflows()`，成功後顯示 `st.toast()`。

### 測試策略

| 測試 | 驗證項目 |
|------|---------|
| `test_sync_workflows_inserts_rows` | workflows 表有新資料 |
| `test_sync_workflows_inserts_steps` | workflow_steps 表步驟正確 |
| `test_sync_workflows_idempotent` | 執行兩次不重複插入 |
| `test_sync_workflows_updates_steps` | yaml 改變後 steps 正確更新 |
| `test_list_workflows_prod_mode` | prod 模式 sync 後 list_workflows() 回傳結果 |

---

## Fix 4 — 在 Runners 中呼叫 `AuthProvider`

### 問題根因

`auth_provider.py` 已實作 `check_permission(plugin_id, action)`，
但兩個 runner 都沒有呼叫它。

### 解法

在 `cv_framework_runner.py` 的執行按鈕回呼中加入：

```python
from auth_provider import AuthProvider

_auth = AuthProvider(db_path=LOG_DIR / "data" / "tools.sqlite")

# 按下「▶ 執行」後，execute_logic 之前：
if not _auth.check_permission(plugin_id, "execute"):
    st.error("您沒有執行此模組的權限。")
    st.stop()
```

在 `workflow_runner.py` 的 `render_step()` 中加入同樣的 check，
使用 `step.plugin_id` 作為 `plugin_id`。

### 設計決策

| 決策 | 選擇 | 理由 |
|------|------|------|
| check 時機 | 按下執行後、`execute_logic` 前 | 不影響 UI 渲染，只攔截執行動作 |
| "view" check | 暫不加 | dev 模式下所有人都是 admin，影響有限；view check 會阻止 UI 顯示，使用者體驗差 |
| `db_path` 來源 | 從 `LOG_DIR` 推導，與 registry 一致 | 不需要額外環境變數 |

### 測試策略

- `auth_provider.py` 本身已有 11 個測試
- Streamlit runner 的 auth check 屬於整合層，用 source code 掃描確認 import + call 存在
- 實際行為測試留待 E2E（需要 Streamlit 執行環境）

---

## 影響範圍摘要

| 檔案 | 變動類型 |
|------|---------|
| `plugin_registry.py` | Fix 2：publish() + _plugin_from_db()；Fix 3：sync_workflows() |
| `tools/workflow_runner.py` | Fix 1：output pane stop；Fix 4：auth check |
| `tools/management_runner.py` | Fix 1：output pane stop；Fix 3：sync workflows 按鈕 |
| `tools/cv_framework_runner.py` | Fix 4：auth check |
| `tests/test_plugin_registry.py` | Fix 2 + 3 的新測試 |
