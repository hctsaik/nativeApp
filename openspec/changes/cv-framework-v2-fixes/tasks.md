# Tasks：CV 框架 v2 修補

## Fix 1 — 單 Pane 輸出 ✅

- [x] `tools/workflow_runner.py`：`main()` 前段加 `CIM_TOOL_LAYER == "output"` 判斷
- [x] `tools/management_runner.py`：同上
- [x] 確認 source code 中含有 layer check（靜態掃描測試 × 2）

## Fix 2 — `publish()` 納入 `plugin.yaml` ✅

- [x] `plugin_registry.py`：`publish()` 同時抓 `plugin.yaml`
- [x] `plugin_registry.py`：`_plugin_from_db()` 從 content_json 讀完整 metadata（name/version/category/description/tags/runner）
- [x] `tests/test_plugin_registry.py`：新增 4 個測試
  - [x] `test_publish_includes_plugin_yaml`
  - [x] `test_plugin_from_db_reads_yaml_version`
  - [x] `test_plugin_from_db_reads_yaml_name`
  - [x] `test_plugin_from_db_fallback_without_yaml`
- [x] `pytest tests/test_plugin_registry.py` 全部通過

## Fix 3 — `sync_workflows()` + Prod 模式 Workflow ✅

- [x] `plugin_registry.py`：實作 `sync_workflows() -> list[str]`（INSERT OR REPLACE + 重建 steps）
- [x] `tools/management_runner.py`：「工作流程」Tab 加「同步 Workflow 到 DB」按鈕
- [x] `tests/test_plugin_registry.py`：新增 7 個測試
  - [x] `test_sync_workflows_inserts_rows`
  - [x] `test_sync_workflows_inserts_steps`
  - [x] `test_sync_workflows_idempotent`
  - [x] `test_sync_workflows_updates_steps`
  - [x] `test_list_workflows_prod_mode`
  - [x] `test_list_workflows_prod_mode_steps`
- [x] `pytest tests/test_plugin_registry.py` 全部通過

## Fix 4 — AuthProvider 在 Runners 呼叫 ✅

- [x] `tools/cv_framework_runner.py`：執行前加 `_auth.check_permission(module_id, "execute")`
- [x] `tools/workflow_runner.py`：`render_step()` 執行前加同樣 check
- [x] 靜態掃描：確認兩個 runner 都 import AuthProvider 且呼叫 check_permission（× 2 tests）

## 收尾 ✅

- [x] 執行完整測試：`pytest tests/ scripts/module_003/ scripts/module_004/ scripts/module_005/ -q` → **308 passed**
- [x] 更新 `openspec/changes/cv-framework-v2-fixes/tasks.md`（本檔）
- [ ] 更新 `sidecar/python-engine/README.md`（補充 auth + sync_workflows 說明）
- [ ] 更新 `memory/current_focus.md`
