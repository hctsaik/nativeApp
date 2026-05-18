# 設計：Portal 工具列表分類顯示

---

## 後端：ToolInfo 加 `category`

### 改動檔案：`sidecar/python-engine/engine.py`

**ToolInfo model 加欄位：**

```python
class ToolInfo(BaseModel):
    tool_id: str
    name: str
    version: str
    category: str = "tool"   # 新增
```

**ToolRegistry.list_tools() 推導 category：**

```python
def _derive_category(tool_id: str) -> str:
    if tool_id.startswith("cvmod-") or tool_id in ("cv-framework", "opencv-tool", "animal-tagger"):
        return "module"
    if tool_id.startswith("workflow-"):
        return "workflow"
    if tool_id.startswith("management-"):
        return "management"
    return "tool"
```

`list_tools()` 在建立 `ToolInfo` 時帶入 `category=_derive_category(tool.tool_id)`。

**API 回傳格式（新）：**

```json
[
  {"tool_id": "cvmod-003", "name": "003 - 不規則邊框產生器", "version": "0.1.0", "category": "module"},
  {"tool_id": "workflow-edge-analysis", "name": "008 - 邊緣品質分析（套件）", "version": "1.0.0", "category": "workflow"},
  {"tool_id": "management-center", "name": "009 - 管理中心", "version": "1.0.0", "category": "management"}
]
```

---

## 前端：`<optgroup>` 分組

### 改動檔案：`apps/portal-react/src/main.jsx`

**分組順序：** module → workflow → management → tool

**`TopBar` 中的 `<select>` 改為：**

```jsx
const CATEGORY_LABELS = {
  module:     "模組",
  workflow:   "工作流程套件",
  management: "管理",
  tool:       "工具",
};
const CATEGORY_ORDER = ["module", "workflow", "management", "tool"];

function groupTools(tools) {
  const groups = {};
  for (const t of tools) {
    const cat = t.category ?? "tool";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(t);
  }
  return groups;
}

// 在 <select> 內：
{(() => {
  const groups = groupTools(tools);
  return CATEGORY_ORDER
    .filter(cat => groups[cat]?.length)
    .map(cat => (
      <optgroup key={cat} label={CATEGORY_LABELS[cat] ?? cat}>
        {groups[cat].map(t => (
          <option key={t.tool_id} value={t.tool_id}>{t.name}</option>
        ))}
      </optgroup>
    ));
})()}
```

---

## 測試策略

| 目標 | 測試方式 |
|------|---------|
| `_derive_category` 正確推導所有已知 tool_id | `tests/test_tool_registry.py` 新增單元測試 |
| `ToolInfo` 回傳含 `category` 欄位 | `tests/test_api.py` 驗證 `/tools` response |
| 前端 optgroup 渲染 | 視覺手動驗收（JSX 無 Streamlit，不適合後端 pytest）|

---

## 設計決策

| 決策 | 選擇 | 理由 |
|------|------|------|
| category 來源 | 從 tool_id 推導，不改 DB | 最小改動；tool_id 命名已有規律，不需新欄位 |
| 舊 `tool_id` 的 category | 硬碼 mapping | opencv-tool / animal-tagger 是歷史工具，數量少且固定 |
| optgroup 排序 | module → workflow → management → tool | 使用頻率高的排前面 |
| 空 category 的 fallback | `"tool"` | 確保未來新 tool_id 不 crash |
