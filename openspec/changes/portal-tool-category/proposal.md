# 變更：Portal 工具列表分類顯示（portal-tool-category）

## 為何需要此變更

目前 Portal 工具下拉選單為平面列表（flat list），所有工具混排：

```
[004 - CV 模組框架]
[002 - 影像資訊讀取]
[003 - 不規則邊框產生器]
[006 - 邊緣完整度偵測]
[007 - 邊緣記錄查詢]
[008 - 邊緣品質分析（套件）]   ← Workflow，長得和 Module 一樣
[009 - 管理中心]                ← 管理工具，沒有視覺區隔
[001 - OpenCV 影像處理]
[005 - 動物影像標記]
```

隨著 Workflow 套件和管理中心的加入，使用者無法直覺區分「可直接執行的單一模組」、「整合套件」與「系統管理工具」。

## 變更目標

- 後端 `/tools` API 回傳 `category` 欄位（`string`）
- 前端下拉選單依 category 分組（HTML `<optgroup>`）
- 不改變現有的啟動流程、IPC 結構、或任何其他行為

## Category 定義

| `category` 值 | 顯示名稱（optgroup label） | 來源 tool_id 前綴 |
|--------------|--------------------------|-----------------|
| `module` | 模組 | `cvmod-`, `cv-framework`, `opencv-tool`, `animal-tagger` |
| `workflow` | 工作流程套件 | `workflow-` |
| `management` | 管理 | `management-` |
| `tool` | 工具（其他） | 其餘 |

## 不納入

- DB 層的 category 欄位（沿用從 tool_id 推導，不改 schema）
- Portal 列表頁面的任何其他視覺改動
- 前端 TypeScript 型別重構
