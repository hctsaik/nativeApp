# Tasks：Portal 工具列表分類顯示

## 後端 ✅

- [x] `engine.py`：`ToolInfo` 加 `category: str = "tool"` 欄位
- [x] `engine.py`：新增 `_derive_category(tool_id)` 函式 + `_MODULE_TOOL_IDS` 常數
- [x] `engine.py`：`ToolRegistry.list_tools()` 帶入 `category`
- [x] `tests/test_tool_registry.py`：`test_list_tools_includes_category` + 13 個 parametrize `test_derive_category`
- [x] `tests/test_api.py`：`test_list_tools_response_shape`（含 category）+ `test_list_tools_category_values`
- [x] `pytest tests/` 全部通過（323 passed）

## 前端 ✅

- [x] `apps/portal-react/src/main.jsx`：新增 `CATEGORY_LABELS` + `CATEGORY_ORDER` 常數
- [x] `apps/portal-react/src/main.jsx`：新增 `groupTools(tools)` helper
- [x] `apps/portal-react/src/main.jsx`：`TopBar` 的 `<select>` 改用 `<optgroup>`
- [x] `fallbackApi.listTools()` 加入 `category: "tool"` 欄位

## 收尾

- [ ] 手動驗收：開啟 Portal，確認下拉選單正確分組（模組 / 工作流程套件 / 管理）
- [x] 更新 `openspec/changes/portal-tool-category/tasks.md`（本檔）
- [x] 更新 `memory/current_focus.md`
