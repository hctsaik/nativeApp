# ADR-003: Schema Pin (Append-only Schema Store)

## Status
Accepted

## Date
2026-05-26

## Context
標注 schema（label classes、attribute 定義）在 annotation set 建立後若發生變更，會導致：
- 已標注的資料與當前 schema 不一致（歷史資料無法驗證）
- 匯出報表時 label mapping 錯誤
- 多人協作時 schema drift 難以追蹤

需要決定 schema 的版本管理策略：允許 in-place mutate，或採用 immutable snapshot。

## Decision
採用 **Append-only schema store**：

- `create_annotation_set` 時，將當時的 schema snapshot 寫入 `annotation_schemas` table（append only，不 UPDATE / DELETE）。
- `annotation_sets.schema_id` 指向 immutable snapshot 的 row ID。
- 若 schema 需要「更新」，只能 INSERT 新版本，由 client 決定是否建立新的 annotation set 指向新版 schema，或保留舊有指向。
- 新增 `schema_version_ref` 欄位到 `annotation_sets`（字串，供 UI 顯示友善版本號），但 Phase 4 不強制使用（可為 NULL）。

Phase 4 先加 `schema_version_ref` 欄位但不強制使用，保持 backward compat。

## Consequences
- **優點**：歷史標注資料永遠可以對應到當時的 schema，驗證邏輯穩定。
- **優點**：schema 變更有完整歷史，便於 audit。
- **優點**：匯出時直接從 snapshot 讀取，不受後來的 schema 變更影響。
- **缺點**：schema 修正（如 typo）無法 in-place 修復，需建立新版本並可能觸發 re-annotation。
- **缺點**：`annotation_schemas` table 只增不減，長期累積需定期 archive（Phase 4 暫不處理）。
- `schema_version_ref` 為 NULL 的舊資料（Phase 3 以前）視為 `v0`，不強制遷移。
