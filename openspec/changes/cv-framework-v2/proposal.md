# 變更：CV 框架 v2 — 外掛系統、工作流程套件與管理中心

## 為何需要此變更

現有的 CV 模組框架（v1）存在以下結構性問題：

1. **框架與外掛耦合**：模組的登記方式（hardcode 在 `engine.py`）讓外掛開發者每次都要修改核心檔案
2. **無版本控制**：腳本直接從檔案系統執行，無法追蹤歷史、無法回溯
3. **無開發 / 生產模式切換**：本地開發與部署行為相同，容易意外影響生產環境
4. **功能碎片化**：module_003 / 004 / 005 是同一工作流程，但 User 必須分開操作三個獨立工具
5. **無權限控制**：所有工具對所有人開放，無法按角色限制存取
6. **無管理介面**：啟用、停用、版本回溯都需要直接操作 DB

## 變更目標

建立乾淨、可擴展的外掛框架，核心原則：

- **框架不知道外掛存在**：外掛透過 manifest 自我描述，框架動態發現
- **版本不可變**：每次發布都是 DB 中的一個不可變快照，永遠可以回溯
- **開發體驗優先**：dev 模式下直接讀取檔案系統，不需要任何 DB 操作
- **使用者體驗優先**：相關模組組成 Workflow，使用者看到的是完整工作流程，不是碎片

## 變更範圍

**Phase 1 — Plugin Manifest + Registry**
- 每個模組有 `plugin.yaml` 自我描述
- 新 DB tables（plugins, plugin_versions, workflows, workflow_steps, roles, plugin_permissions）
- `plugin_registry.py` 核心載入邏輯

**Phase 2 — Dev/Prod 雙模式**
- `plugin_loader.py`：`CIM_DEV_MODE=1` → 讀檔案系統；`0` → 讀 DB
- `cv_framework_runner.py` 改用 loader

**Phase 3 — Workflow / Suite**
- `workflow.yaml` 定義多模組套件
- `workflow_runner.py`：Tab 式 UI，步驟間狀態自動傳遞
- edge_analysis workflow 整合 module_003/004/005

**Phase 4 — Auth Placeholder**
- `auth_provider.py`：interface 預留給未來 web service，現在回傳 admin 角色
- Plugin 執行前先過 permission check

**Phase 5 — Management Center**
- `tools/management_runner.py`：獨立 Streamlit 管理工具
- 功能：外掛列表、版本歷史、回溯、啟用/停用、Dev→Prod 發布

**Phase 6 — 全模組 Migration**
- module_001–005 全部加 `plugin.yaml`
- engine.py 改用 `PluginRegistry`，移除 hardcode seed
- 舊 `tools` 表保留但不再直接使用（兼容現有 Portal）

**不納入：**
- 實際的 web service 帳號整合（留待 Production 環境）
- E2E 測試
- 前端 Portal UI 改動（Portal 繼續透過 `/tools` API 取得工具列表）
