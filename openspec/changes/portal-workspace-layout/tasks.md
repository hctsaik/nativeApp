# 任務：Portal Workspace 版面重新設計

## 1. shared-protocol 更新

- [x] 在 `packages/shared-protocol/src/index.js` 新增 `EXECUTE_START`、`EXECUTE_COMPLETE`、`DISPLAY_UPDATE` 三個 MessageType
- [x] 更新 `packages/shared-protocol/src/index.test.js` 確認新 MessageType 存在且 `isProtocolMessage` 能驗證

## 2. Portal CSS 重構（`apps/portal-react/src/styles.css`）

- [x] 移除 `.shell`（grid）、`.sidebar`、`.brand`（sidebar 版）、`.nav` 樣式
- [x] 新增 `.workspace`（flex column）
- [x] 新增 `.workspace-body`（flex row，左右分割）
- [x] 新增 `.left-panel`（flex 0 0 38%，含 position: relative）
- [x] 新增 `.tab-bar`、`.tab`、`.tab.active`
- [x] 新增 `.tab-content`（flex 1，iframe 全高）
- [x] 新增 `.loading-overlay`（position absolute，半透明）
- [x] 新增 `.right-panel`（flex 1，居中對齊）
- [x] 新增 `.display-image`、`.display-empty`
- [x] 新增 `.top-bar-brand`
- [x] 調整 `.toolbar`（移除依賴 sidebar 的間距設定）

## 3. Portal React 重構（`apps/portal-react/src/main.jsx`）

- [x] 移除 `activeMode` state 與相關邏輯（sidebar mode 切換）
- [x] 移除 `<aside class="sidebar">` 元件
- [x] 新增 `activeTab` state（`"input" | "output"`，預設 `"input"`）
- [x] 新增 `isExecuting` state（`boolean`，預設 `false`）
- [x] 新增 `displayImageUrl` state（`string | null`）
- [x] 將 `<main class="content">` 改為 `<div class="workspace">`
- [x] 實作 `<TopBar>` 內嵌 brand 文字
- [x] 實作 `<WorkspaceBody>` 含 `<LeftPanel>` 與 `<RightPanel>`
- [x] 實作 `<LeftPanel>`：TabBar + TabContent + LoadingOverlay
- [x] 實作 `<RightPanel>`：依 activeTab 和 displayImageUrl 決定顯示內容
  - Input tab + selectedPaths[0] → `<img src="file://...">`
  - Output tab + displayImageUrl → `<img src={displayImageUrl}>`
  - 其他 → empty state
- [x] 更新 `onMessage` handler 處理 `EXECUTE_START`、`EXECUTE_COMPLETE`、`DISPLAY_UPDATE`
- [x] 移除 `enterpriseSrcDoc`、`sendHostNavigate`（Mode 2 mock 整合進新框架）

## 4. Sidecar engine.py 更新

- [x] `ToolStartResponse` 改為 `{ tool_id, input_url, output_url, input_port, output_port }`
- [x] `ToolProcessManager` 改為啟動兩個 Streamlit process（input / output）
- [x] 新增 `_split_scripts()` 自動判斷 `{stem}_input.py` / `{stem}_output.py` 是否存在（fallback 用同一個 script）
- [x] `streamlit_command` 改為 `streamlit_command_for_script(script, port, log_dir)`
- [x] `--run-streamlit-tool` 改為 `--run-streamlit-script <path>`
- [x] 更新 `sidecar/python-engine/tests/test_api.py` 配合新 response shape

## 5. 手動驗收

- [ ] 啟動 app，確認 Top Bar 正常顯示品牌 + 功能選擇
- [ ] 啟動 opencv-tool，確認 Input tab 顯示 Streamlit iframe
- [ ] 選擇影像，確認 Right Panel 顯示 Input 預覽影像
- [ ] Output tab 在執行前顯示 empty state
- [ ] 現有 Streamlit 功能（影像處理）不受影響

## 6. 測試更新

- [x] `packages/shared-protocol/src/index.test.js` 新增測試：新 MessageType 皆存在
- [x] 執行 `npm test`，確認全部通過（29 tests）
