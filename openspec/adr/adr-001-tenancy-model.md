# ADR-001: Tenancy Model

## Status
Accepted

## Date
2026-05-26

## Context
CIM 平台需要支援多租戶情境：同一個 annotation 資料庫可能儲存來自不同專案或組織的資料。
需要決定以哪一層隔離租戶資料：資料庫層（DB-level Row-Level Security）或應用服務層（application-level filtering）。

主要選項：
1. **DB-level RLS**：PostgreSQL RLS 或 SQLite ATTACH per-tenant。隔離強，但 SQLite 不原生支援 RLS，且切換 DB 檔案複雜度高。
2. **Row-level isolation（application layer）**：所有共用 table 加 `tenant_id` 欄位，服務層每次查詢都附加 WHERE 條件。實作簡單，SQLite 友善。

## Decision
採用 **Row-level isolation**：

- 所有涉及租戶資料的 table 加 `tenant_id TEXT NOT NULL DEFAULT ''` 欄位。
- 服務層（`services.py` 及 use-case 層）負責在所有 SELECT / UPDATE / DELETE 查詢附加 `WHERE tenant_id = :tenant_id`。
- `tenant_id` 由呼叫端在 API request context 傳入，不由 DB engine 自動注入。
- `DEFAULT ''` 保留向後相容，空字串視為「無租戶限制」的 legacy 資料。

## Consequences
- **優點**：對 SQLite 零額外依賴，遷移現有 schema 只需 ALTER TABLE ADD COLUMN。
- **優點**：服務層程式碼可審計，WHERE 條件一目了然。
- **缺點**：若服務層忘記加 WHERE 條件，資料會跨租戶洩漏（需 code review 把關）。
- **缺點**：無法利用 DB engine 強制隔離，需靠測試與靜態分析補強。
- Phase 4 先以 `tenant_id = ''`（空字串）作為預設值，不強制 multi-tenant，保持 backward compat。
