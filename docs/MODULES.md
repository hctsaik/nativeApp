# 模組參考文件索引

> 本文件已重組為模組化結構。各模組完整文件請見下方連結。
> 最後更新：2026-05-29（新增 module_026；標記 module_010/019/022/023/024/025 為廢棄）

---

## 文件結構

```
docs/
├── README.md                    ← 平台安裝、啟動、測試指南
├── MODULES.md                   ← 本索引文件
├── platform/
│   ├── ARCHITECTURE.md          ← 系統架構、模組系統概觀、如何新增模組
│   ├── system-flow.md           ← 系統流程圖
│   └── AI_CONTEXT.md            ← AI 輔助開發情境
├── components/
│   └── ANNOTATION_XANYLABELING.md  ← X-AnyLabeling 標注整合
└── modules/
    ├── README.md                ← 模組目錄索引
    ├── module_001.md
    ├── module_002.md
    ├── module_003.md
    ├── module_004.md
    ├── module_005.md
    ├── module_006.md
    ├── module_008.md
    ├── module_010.md
    ├── module_012.md
    ├── module_013.md
    ├── module_014.md
    ├── module_015.md
    ├── module_016.md
    ├── module_017.md
    ├── module_018.md
    ├── sheet-annotation_workflow.md
    ├── sheet_edge_analysis.md
    └── management_center.md

scripts/module_XXX/
├── README.md                    ← 開發者快速參考（API、合約、設定）
└── guide.html                   ← 使用者操作指南（嵌入於 Input 頁面）
```

---

## 快速跳轉

| 模組 | 技術文件 | 開發者參考 | 使用者指南 |
|---|---|---|---|
| Module 001 - OpenCV 影像處理 | [module_001.md](modules/module_001.md) | — | — |
| Module 002 - 影像資訊讀取 | [module_002.md](modules/module_002.md) | — | — |
| Module 003 - 不規則邊框產生器 | [module_003.md](modules/module_003.md) | — | — |
| Module 004 - 邊緣完整度偵測 | [module_004.md](modules/module_004.md) | — | — |
| Module 005 - 邊緣記錄查詢 | [module_005.md](modules/module_005.md) | — | — |
| Module 006 - 動物影像標記 | [module_006.md](modules/module_006.md) | [scripts/module_006/README.md](../sidecar/python-engine/scripts/module_006/README.md) | guide.html（嵌入 App）|
| Module 008 - 影片追蹤標注 | [module_008.md](modules/module_008.md) | [scripts/module_008/README.md](../sidecar/python-engine/scripts/module_008/README.md) | guide.html（嵌入 App）|
| Module 010 - Data Feeder ⚠️ **廢棄** | [module_010.md](modules/module_010.md) | — | — |
| Module 012 - 標注工作台 | [module_012.md](modules/module_012.md) | — | — |
| Module 013 - Sync Back | [module_013.md](modules/module_013.md) | — | — |
| Module 014 - 匯出 / 回傳 | [module_014.md](modules/module_014.md) | — | — |
| Module 015 - Dashboard | [module_015.md](modules/module_015.md) | — | — |
| Module 016 - AI Pre-labeling | [module_016.md](modules/module_016.md) | — | — |
| Module 017 - Label Manager | [module_017.md](modules/module_017.md) | — | — |
| Module 018 - 審查 Gallery | [module_018.md](modules/module_018.md) | — | — |
| Module 019 - Data Downloader ⚠️ **廢棄** | — | — | — |
| Module 022 - 標註權限管理 ⚠️ **廢棄** | — | — | — |
| Module 023 - 標註任務 ⚠️ **廢棄** | — | — | — |
| Module 024 - 標注工作台（iWISC 版）⚠️ **廢棄** | — | — | — |
| Module 025 - 完成報表 ⚠️ **廢棄** | — | — | — |
| Module 026 - 資料來源（新）| — | — | — |
| Sheet - 🐜 影像標註（統一架構）| [sheet-annotation_workflow.md](modules/sheet-annotation_workflow.md) | — | — |
| Sheet - 邊緣品質分析 | [sheet_edge_analysis.md](modules/sheet_edge_analysis.md) | — | — |
| 管理中心 | [management_center.md](modules/management_center.md) | — | — |

---

## 平台層文件

- [平台架構總覽](platform/ARCHITECTURE.md)：系統架構、cv_framework_runner、DEV/PROD 模式、如何新增模組
- [系統流程圖](platform/system-flow.md)：Electron ↔ React ↔ Python 通訊流程
- [AI 輔助開發情境](platform/AI_CONTEXT.md)：AI 協作開發指引

## 共用元件文件

- [X-AnyLabeling 標注整合](components/ANNOTATION_XANYLABELING.md)：annotation-core、MCP tools、X-AnyLabeling 工作流程
