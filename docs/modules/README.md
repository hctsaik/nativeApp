# 模組目錄

> 每個模組的完整技術文件請見各自的 `module_XXX.md`。
> 模組的操作指南（給終端使用者）請見 `scripts/module_XXX/guide.html`。
> 模組的開發者參考請見 `scripts/module_XXX/README.md`。

---

## 模組清單

| ID | 名稱 | Runner | 狀態 | 文件 |
|---|---|---|---|---|
| module_001 | OpenCV 影像處理 | cv_framework | 啟用 | [module_001.md](module_001.md) |
| module_002 | 影像資訊讀取 | cv_framework | 停用（Sheet 專用）| [module_002.md](module_002.md) |
| module_003 | 不規則邊框產生器 | cv_framework | 啟用 | [module_003.md](module_003.md) |
| module_004 | 邊緣完整度偵測 | cv_framework | 啟用 | [module_004.md](module_004.md) |
| module_005 | 邊緣記錄查詢 | cv_framework | 啟用 | [module_005.md](module_005.md) |
| module_006 | 動物影像標記 | cv_framework | 啟用 | [module_006.md](module_006.md) |
| module_008 | 影片追蹤標注 | cv_framework | 啟用 | [module_008.md](module_008.md) |
| module_009 | 統一標注平台 | annotation_runner | 啟用 | [module_009.md](module_009.md) |
| module_010 | Data Feeder | cv_framework | 啟用 | [module_010.md](module_010.md) |
| module_012 | Annotation Session | cv_framework | 啟用 | [module_012.md](module_012.md) |
| module_013 | Update | cv_framework | 啟用 | [module_013.md](module_013.md) |
| sheet-annotation_workflow | 標注作業流程（套件）| sheet_runner | 啟用 | [sheet-annotation_workflow.md](sheet-annotation_workflow.md) |
| sheet-edge-analysis | 邊緣品質分析（套件）| sheet_runner | 啟用 | [sheet_edge_analysis.md](sheet_edge_analysis.md) |
| management-center | 管理中心 | management_runner | 啟用 | [management_center.md](management_center.md) |

---

## 平台架構

- [平台架構總覽](../platform/ARCHITECTURE.md)
- [系統流程圖](../platform/system-flow.md)
- [AI 輔助開發情境](../platform/AI_CONTEXT.md)

## 共用元件

- [X-AnyLabeling 標注整合](../components/ANNOTATION_XANYLABELING.md)

## 如何新增模組

見 [平台架構總覽](../platform/ARCHITECTURE.md) §新增模組流程。
