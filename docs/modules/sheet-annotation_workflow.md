# sheet-annotation — 影像標註（統一架構）

> 最後更新：2026-05-29（重構為 4-tab 統一架構）

## Overview

`sheet-annotation`（🐜 影像標註）是統一標注工作流 Sheet，由 `sidecar/python-engine/sheets/annotation.yaml` 驅動。支援**本地資料夾**與**外部任務系統（如 iWISC）**兩種資料來源，並整合標注、審查、匯出/回傳於同一 Sheet 中。

## 架構設計

Sheet 配置由 `sheets/annotation.yaml` 定義（不再硬編碼於 engine.py），共 4 個 tab：

| Order | Module | Label | 說明 |
|------:|--------|-------|------|
| 0 | `module_026` | 📥 資料來源 | 統一資料來源入口：本地資料夾或外部任務系統（iWISC），輸出 DatasetManifest |
| 1 | `module_012` | ✏️ 標注工作台 | 開啟 X-AnyLabeling/LabelMe 等標注工具進行標注作業 |
| 2 | `module_018` | 🖼️ 審查 | Grid 縮略圖 + BBox overlay 快速審查標注結果，標記 rework |
| 3 | `module_014` | 📤 匯出 / 回傳 | 匯出訓練格式（COCO/YOLO/Pascal VOC/ImageFolder/CSV）或回傳至 iWISC |

## 資料來源模式（module_026）

### 📁 本地資料夾
- 選擇本地圖片資料夾，遞迴掃描指定副檔名
- 輸出 DatasetManifest 供後續 tab 使用

### 🔌 外部任務系統（iWISC）
- 選擇已註冊的 SystemTenant（外部系統連線）
- 瀏覽公海任務清單，選取並認領任務（ant_active 0→1）
- 自動下載任務 ZIP、解壓 images/、解析 annotations.json
- 儲存 original_annotation_json（不可覆蓋的原始快照）

> iWISC 是「外部任務系統」的其中一種實作，透過 `annotation/integrations/connectors/rest_connector.py` 與平台介面溝通。

## 核心元件

| 元件 | 路徑 |
|------|------|
| Sheet 配置 | `sidecar/python-engine/sheets/annotation.yaml` |
| Service 層 | `sidecar/python-engine/annotation/services.py` |
| ORM Models | `sidecar/python-engine/annotation/core/models.py` |
| SQLite Store | `sidecar/python-engine/annotation/storage/sqlite_store.py` |
| Workspace | `sidecar/python-engine/annotation/storage/workspace.py` |
| RestConnector | `sidecar/python-engine/annotation/integrations/connectors/rest_connector.py` |
| MCP Server | `mcp/annotation_mcp/server.py` |

## 共用資料路徑

| 路徑 | 用途 |
|------|------|
| `{CIM_LOG_DIR}/config/shared.json` | 各 tab 之間傳遞最新 manifest 資訊（manifest_id、iwsc_task_id 等） |
| `{CIM_LOG_DIR}/db/manifest.sqlite` | DatasetManifest、items、exports、sync queue、snapshots |
| `{CIM_LOG_DIR}/config/module_012_classifications_*.json` | 圖片層級分類標記 |
| `{CIM_LOG_DIR}/xanylabeling_state/` | X-AnyLabeling 執行狀態 |
| `{image_dir}/{image_stem}.json` | X-AnyLabeling/LabelMe annotation JSON |
| `{CIM_LOG_DIR}/annotation_workspace` | iWISC 任務 workspace（annotation-core） |

## Workspace 路徑（annotation-core）

| 環境 | 路徑 |
|------|------|
| Streamlit modules（由 engine 注入） | `{CIM_LOG_DIR}/annotation_workspace` |
| MCP server（`.mcp.json` 設定） | `apps/host-electron/logs/annotation_workspace` |
| 兩者在 dev 模式下指向同一位置 | ✅ |

## 標注生命週期（iWISC 外部任務模式）

```
Phase 0  外部系統設定（管理中心 → 標註權限管理）
  └─ register_tenant / add_user_to_tenant

Phase 1  任務發現 + 認領（module_026 → 外部任務系統模式）
  └─ GET {server_host}/getAntList → 公海列表
  └─ 選取任務 → 點「執行」 → 認領（ant_active 0→1）+ 下載 ZIP

Phase 2  標注（module_012）
  └─ 解壓 images/ + 解析 annotations.json
  └─ 儲存 original_annotation_json（不可覆蓋）
  └─ 使用 X-AnyLabeling 完成標注

Phase 3  審查（module_018）
  └─ Grid 瀏覽，標記需重工項目

Phase 4  回傳（module_014）
  └─ POST {server_host}/tasks/{ant_id}/result（deliver_result）
  └─ 或匯出本地訓練格式
```

## 已廢棄的舊模組（勿使用）

以下模組屬於舊架構，已標記 `enabled: false`，程式碼保留但不再載入於 Sheet：

| 模組 | 廢棄原因 |
|------|---------|
| `module_010` Data Feeder | 整合至 module_026 本地資料夾模式 |
| `module_019` Data Downloader | 整合至 module_026 外部任務系統模式 |
| `module_022` 標註權限管理 | 移至管理中心（待完整實作） |
| `module_023` 標註任務 | 整合至 module_026 外部任務系統模式 |
| `module_024` 標注工作台（iWISC 版） | 整合至 module_012 通用版 |
| `module_025` 完成報表 | 整合至 module_014 匯出/回傳 |

## 待完成

- RBAC 強制執行：`is_user_authorized()` 已在 DB 層備妥，但 MCP/API 路徑尚未強制呼叫
- Tenant 管理 MCP tools（`register_tenant`、`add_user_to_tenant`）未暴露於 `server.py`
- 管理中心的「標註權限管理」UI（module_022 的功能）尚未完整移植
