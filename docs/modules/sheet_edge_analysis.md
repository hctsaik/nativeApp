# Sheet：邊緣品質分析

## 概要

| 項目 | 值 |
|---|---|
| **sheet_id** | `edge_analysis`（DB 中為 `sheet-edge-analysis`）|
| **名稱** | 邊緣品質分析（套件）|
| **runner** | `sheet_runner.py` |
| **定義檔** | `scripts/sheets/edge_analysis/sheet.yaml` |

整合邊框生成、偵測與歷史查詢的多分頁工作流程。

---

## 分頁組成

```yaml
tabs:
  - plugin_id: module_003
    label: 影像來源
  - plugin_id: module_004
    label: 偵測分析
  - plugin_id: module_005
    label: 歷史查詢
```

---

## 典型工作流程

```
1. 「影像來源」分頁 → 調整參數 → ▶ 執行 → 產生合成邊框影像 → 下載 PNG
2. 「偵測分析」分頁 → 上傳 PNG → 輸入 Parts 編號 → ▶ 執行 → 儲存至 SQLite
3. 「歷史查詢」分頁 → 選擇日期範圍 → ▶ 執行 → 查看記錄 → 匯出 CSV
```

---

## Sheet Runner vs cv_framework_runner

| 特性 | cv_framework_runner | sheet_runner |
|---|---|---|
| 分頁數 | 2 頁（Input / Output）| N 頁（sheet.yaml 定義）|
| 結果持久化 | 寫入 `{tool_id}_result.json` | 存在 `session_state`，重整即消失 |
| 執行按鈕 | 一個（Input 頁）| 每個分頁各自有 ▶ 執行 |
