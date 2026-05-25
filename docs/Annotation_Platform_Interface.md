
# Master System Specification: Industrial Vision Annotation Platform

## 1. Executive Summary
本專案為一個工業級影像標註平台，採用 **Spec-Driven Design** 與 **非同步包裹交換 (Async Data-Shipping)** 架構。
平台核心精神為「絕對標準化」：平台不配合外部系統（如 MES、ERP）開發客製化 DB Connector，而是要求外部系統實作標準 API 契約，並透過 ZIP 壓縮檔進行影像與標註資料的交換。

## 2. Architecture Principles
* **Platform-Dictated (平台強勢主導):** 外部系統必須完全遵守平台的 API 契約與 ZIP 目錄結構。
* **Zero-Customization (核心零客製化):** 平台內部維持單一 Canonical Model。外部系統特有欄位（如 Lot ID, EQP ID）統一封裝於 `external_context` (JSON)，平台僅負責透傳與前端顯示，不進行關聯運算。
* **Self-Service Push (自助式取貨):** 平台標註完成後不主動 Call API 推播，而是由外部系統負責人登入平台 Dashboard，透過 GUI 點擊打包下載最新結果。

## 3. Role-Based Access Control (RBAC) & Tenancy
系統採多租戶 (Multi-Tenant) 隔離設計。

* **Role: CIM Sponsor (系統負責人 / Tenant Admin)**
  * 擁有該註冊系統的全局視角。
  * 可登入 Dashboard 查看旗下所有 `antID` 任務的標註完成率。
  * 擁有透過 GUI 下載最終標註 ZIP 包裹的權限。
  * 可在 GUI 上動態維護該系統的「授權標註人員 (User) 名單」。

* **Role: User (標註作業員 / Annotator)**
  * 登入後僅能看見自己被授權的系統。
  * 進入系統後，看見「公海任務列表 (TaskList)」，可自由點擊進入標註。
  * 無權查看 Dashboard 統計與下載 ZIP。

## 4. Core Database Schema (Canonical Model)
實作 ORM 模型時，請嚴格遵守以下結構（需加上 createdAt, updatedAt 等基礎欄位）：

### Table: `SystemTenant` (註冊的外部系統)
* `tenant_id` (UUID, Primary Key)
* `system_name` (String, Unique)
* `server_host_name` (String, 外部系統的 API Base URL)
* `target_format` (String, 該系統期望的標註格式，如 'COCO', 'YOLO')

### Table: `TenantUserMapping` (授權人員白名單)
* `tenant_id` (UUID, Foreign Key)
* `user_id` (String/UUID, 員工工號或系統帳號)

### Table: `AnnotationTask` (核心任務表)
* `task_id` (UUID, Internal Primary Key)
* `tenant_id` (UUID, Foreign Key)
* `antID` (String, 外部系統的唯一任務碼)
* `original_classification` (String, Nullable, 收件時的初始分類)
* `new_classification` (String, Nullable, User 標註後的新分類)
* `annotation_json` (JSON, 平台標準化標註座標與內容)
* `external_context` (JSON, 外部系統專屬逃生艙欄位，平台不解析)
* `antActive` (Integer, 狀態機：0=Pending, 1=Processing, 2=Completed)
* `annotated_by` (String, 最終執行標註的 user_id, Nullable)

## 5. The 4-Phase Lifecycle (Core Workflows)

### Phase 0: Offline Registration (線下註冊)
* 平台管理員為外部系統建立 `SystemTenant`，輸入 `Server_Host_Name` 與 `Target_Format`。
* 寫入初始的 `TenantUserMapping` (白名單)。
* 系統核發該 Tenant 專屬的 API Token，供後續驗證使用。

### Phase 1: Task Discovery (輕量任務發現)
* **觸發點:** User 點選進入特定系統的公海。
* **平台動作:** 發送 `GET {Server_Host_Name}/getAntList`。
* **外部系統回應 (JSON Array):**
  ```json
  [
    {
      "antID": "TASK_123",
      "antActive": 0,
      "antPeriod": "2026-05-26T12:00:00Z",
      "external_context": {"lot_id": "L123", "eqp_id": "AOI-01"}
    }
  ]
平台處理: 渲染 GUI 列表。external_context 僅供顯示。

Phase 2: Async Payload Pull (非同步包裹拉取)
觸發點: User 於公海點擊特定 antID 開始標註。

平台動作: 發送 POST {Server_Host_Name}/getAntTaskDetail。

JSON
{
  "antID": "TASK_123", 
  "format": "COCO"
}
外部系統回應: 回傳非同步下載連結。

JSON
{
  "download_url": "[https://external.local/files/ticket_8899.zip](https://external.local/files/ticket_8899.zip)"
}
平台背景處理:

透過 download_url 下載 ZIP 並串流解壓縮。

驗證結構 (需含 images/ 目錄與標註 json 檔)。

將資料轉譯並 Upsert 入 AnnotationTask 表，開啟標註 GUI 供 User 作業。

Phase 3: Self-Service Push (自助打包取貨)
觸發點: CIM Sponsor 登入 Dashboard 點擊特定任務的【下載結果】。

平台動作: 提供 GUI 讓其選擇下載模式：

mode=orig_img_orig_ant (原始影像 + 原始標註)

mode=orig_img_new_ant (原始影像 + 新的標註)

打包規則: 平台動態產生 ZIP 供下載。標註 JSON 需還原原始的 external_context，並外加 annotated_by 欄位供 CIM 追溯 KPI。

6. Dummy SDK / Reference Implementation
為降低外部系統對接門檻，需開發一組 dummy_sdk 目錄：

Mock Server: 實作接收 getAntList 與 getAntTaskDetail 的基礎 API，展示如何回應平台請求。

Payload Builder: 示範外部系統如何將資料庫圖片與 JSON 打包為平台規定的 ZIP 格式。

Downloader Client: 示範外部系統如何利用腳本呼叫平台 API，自動下載 Phase 3 的完工 ZIP 並解壓縮回寫其自身 DB（供未來自動化擴充使用）。

7. AI Execution Strategy (Phase-by-Phase)
開發時請嚴格遵守以下順序，每個 Phase 完成後需請求人類開發者驗證，禁止一次性生成全域代碼：

[Step 1: Core Data Layer] 建立 ORM Models (SystemTenant, TenantUserMapping, AnnotationTask) 與 Database Migrations。

[Step 2: RBAC & Auth] 實作權限 Middleware，確保 User 僅能存取白名單內的 Tenant 資料。

[Step 3: Ingestion Engine (Phase 1 & 2)] 實作對外 API 請求 (getAntList, getAntTaskDetail)、ZIP 背景下載、防禦性解壓縮與資料入庫邏輯。

[Step 4: Export Engine (Phase 3)] 實作 Dashboard 統計查詢與 ZIP 動態打包下載 API。

[Step 5: External SDK] 撰寫 dummy_sdk 範例程式碼。