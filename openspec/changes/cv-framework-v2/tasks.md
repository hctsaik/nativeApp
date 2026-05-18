# Tasks：CV 框架 v2

## Phase 1 — Plugin Manifest + Registry ✅

- [x] 為 module_001 建立 `scripts/module_001/plugin.yaml`
- [x] 為 module_002 建立 `scripts/module_002/plugin.yaml`
- [x] 為 module_003 建立 `scripts/module_003/plugin.yaml`
- [x] 為 module_004 建立 `scripts/module_004/plugin.yaml`
- [x] 為 module_005 建立 `scripts/module_005/plugin.yaml`
- [x] 建立 `scripts/workflows/edge_analysis/workflow.yaml`
- [x] 撰寫 `plugin_registry.py`（含 DB migration：6 張新表格）
- [x] 撰寫 `tests/test_plugin_registry.py`（27 tests，全部通過）
- [x] 執行 `pytest tests/test_plugin_registry.py` 全部通過

## Phase 2 — Dev/Prod 雙模式 Loader ✅

- [x] 撰寫 `plugin_loader.py`（`load_module_dev` / `load_module_prod` / `is_dev_mode`）
- [x] 更新 `tools/cv_framework_runner.py` 改用 `PluginLoader`
- [x] 撰寫 `tests/test_plugin_loader.py`（16 tests，全部通過）
- [x] 執行 `pytest tests/test_plugin_loader.py` 全部通過
- [ ] 手動驗收：CIM_DEV_MODE=1 + 0 各啟動一次框架，確認行為一致

## Phase 3 — Workflow / Suite ✅

- [x] 撰寫 `tools/workflow_runner.py`（Tab UI + session_state 步驟傳遞）
- [x] 在 `engine.py` 的 `_make_env()` 新增 workflow category 支援（注入 `CIM_WORKFLOW_ID`）
- [x] 在 `engine.py` seed 加入 `edge_analysis` workflow tool + management-center tool
- [ ] 手動驗收：啟動 edge_analysis workflow，003→004 影像自動帶入，005 顯示查詢

## Phase 4 — Auth Placeholder ✅

- [x] 撰寫 `auth_provider.py`（`get_current_role` 永遠回傳 'admin'；`check_permission` 查 DB）
- [x] 撰寫 `tests/test_auth_provider.py`（11 tests，全部通過）
- [x] 執行 `pytest tests/test_auth_provider.py` 全部通過
- [ ] 在 `cv_framework_runner.py` + `workflow_runner.py` 執行前加入 permission check（可留待 Production 前）

## Phase 5 — Management Center ✅

- [x] 撰寫 `tools/management_runner.py`
  - [x] 外掛列表（含狀態、版本、類別）
  - [x] 啟用 / 停用切換
  - [x] 版本歷史展開 + changelog 顯示
  - [x] 版本回溯（設為 active）
  - [x] Dev→Prod 發布（掃描檔案系統 → 打包 content_json → INSERT plugin_versions）
  - [x] 工作流程列表 + 啟用/停用
  - [x] 權限設定 placeholder UI
- [x] 在 `engine.py` 新增 management_center tool seed
- [ ] 手動驗收：Management Center 完整走一遍所有功能

## Phase 6 — 全模組 Migration + 收尾

- [x] 修正 `tests/test_sqlite_adapter.py` 中 name 斷言（對齊實際 seed）
- [x] 執行所有測試：`pytest tests/ scripts/module_003/ scripts/module_004/ scripts/module_005/` → **294 passed**
- [ ] 更新 `README.md`（架構章節、Dev/Prod 切換說明、Management Center 入口）
- [ ] 手動驗收所有新工具
- [ ] 更新 `openspec/changes/cv-framework-v2/design.md`（若有任何設計偏差）
- [ ] 更新 `memory/current_focus.md`
