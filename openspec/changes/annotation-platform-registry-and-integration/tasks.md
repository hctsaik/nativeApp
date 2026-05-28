# Tasks

## Phase 0 — Pre-flight Decisions (blocking Phase 4)

- [ ] 0-A. 決定 Tenancy Model（row-level / schema-level / DB-level）並寫入 `openspec/adr/adr-001-tenancy-model.md`
- [ ] 0-B. 決定 Credential 管理架構（local CredentialStore / external vault）並寫入 `openspec/adr/adr-002-credential-management.md`
- [ ] 0-C. 決定 Schema Pin 機制（append-only schema + `schema_version_ref`）並寫入 `openspec/adr/adr-003-schema-pin.md`

---

## Phase 1 — FormatRegistry

- [x] 1-1. 新增 `tests/annotation/test_format_registry.py`（failing tests first）
  - `test_register_and_get_by_id`
  - `test_get_by_alias_normalizes`
  - `test_unknown_format_raises_value_error`
  - `test_coco_requires_asset_false`
  - `test_list_supported_shape_matches_legacy`
  - `test_all_builtins_registered`
- [x] 1-2. 建立 `annotation/formats/contracts.py`（`FormatCapabilities`, `FormatDescriptor`, `FormatAdapter` Protocol）
- [x] 1-3. 建立 `annotation/formats/registry.py`（`FormatRegistry` singleton, `register`, `get`, `normalize`, `list_supported`）
- [x] 1-4. 建立 `annotation/formats/builtins.py`（6 個 adapter 的 `FormatDescriptor` + 自動 register）
- [x] 1-5. 修改 `services.py`：
  - 移除 10 個 adapter import（lines 6–13），改為 `from annotation.formats.registry import get_format_registry`
  - `supported_annotation_formats()` 改讀 `registry.list_supported()`
  - `import_annotations()` dispatch 改用 registry；COCO `requires_asset=False` 透過 `FormatCapabilities` 決定
  - `import_project_labels()` dispatch 改用 registry
  - `create_export()` dispatch 改用 registry
  - 刪除 `_normalize_format()`（lines 462–475），所有呼叫改為 `registry.normalize()`
- [x] 1-6. 跑 `npm run test:python`，確認既有 `test_services.py` / `test_adapters.py` 全過
- [x] 1-7. 確認 `supported_annotation_formats()` 回傳結果與舊版完全相同
- [x] 1-8. 更新 OpenSpec tasks（本檔）與 design.md 備忘事項

---

## Phase 2 — Structured ConversionReport + Dry-run Export

- [ ] 2-1. 新增 `tests/annotation/test_conversion_report.py`（failing tests first）
  - `test_lossentry_fields`
  - `test_report_summary_lossless`
  - `test_report_summary_warnings`
  - `test_report_summary_errors`
  - `test_backwards_compat_no_losses_field`
- [ ] 2-2. 新增 `tests/annotation/test_dry_run_export.py`（failing tests first）
  - `test_dry_run_does_not_write_files`
  - `test_dry_run_isat_reports_bbox_approximation`
  - `test_dry_run_coco_reports_rle_unsupported`
  - `test_dry_run_yolo_det_reports_polygon_dropped`
  - `test_dry_run_lossless_for_labelme`
- [ ] 2-3. 擴充 `annotation/core/models.py`：新增 `LossEntry` dataclass；在 `ConversionReport` 末端追加 `losses`, `mapping_version`, `summary` 三個欄位（預設值確保向後相容）
- [ ] 2-4. 修改 4 個 adapter（`isat.py`, `coco.py`, `yolo_detection.py`, `yolo_segmentation.py`）：emit 結構化 `LossEntry` 並同時保留舊欄位（`dropped_fields`, `warnings` 等）
- [ ] 2-5. 新增 `AnnotationService.dry_run_export(annotation_set_id, format, options?)` 服務方法（不寫任何檔案）
- [ ] 2-6. 新增 MCP tool `annotation_dry_run_export` 至 `handlers.py`
- [ ] 2-7. 跑 `npm run test:python`，確認既有 export tests 全過

---

## Phase 3 — ToolRegistry

- [ ] 3-1. 新增 `tests/annotation/test_tool_registry.py`（failing tests first）
  - `test_register_and_get_by_id`
  - `test_get_by_alias_normalizes`
  - `test_unknown_tool_raises_value_error`
  - `test_isat_supports_project_mode_false`
- [ ] 3-2. 新增 `tests/annotation/test_tool_launch.py`（failing tests first）
  - `test_labelme_path_join_no_backslash`（regression for line 432 bug）
  - `test_wdac_bypass_uses_sys_path_insert`
  - `test_launch_file_vs_project_output_paths`
- [ ] 3-3. **修 bug**：`012_output.py` `_launch_labelme()` line 432，`\` 改為 `/`
- [ ] 3-4. 建立 `annotation/tools/contracts.py`（`RuntimeStatus`, `ToolDescriptor`, `LabelingToolAdapter` Protocol）
- [ ] 3-5. 建立 `annotation/tools/registry.py`（`ToolRegistry` singleton, `register`, `get`, `normalize`, `list_supported`）
- [ ] 3-6. 建立 `annotation/tools/builtins.py`（x-anylabeling, labelme, isat adapters；WDAC bypass 統一使用 `sys.path.insert` 形式）
- [ ] 3-7. 修改 `labeling_runtime.py`：`detect_labeling_tool()` 和 `launch_labeling_project()` 改用 ToolRegistry dispatch
- [ ] 3-8. 修改 `xanylabeling_runtime.py`：舊 `_command_prefix()` 改為 fallback；新版 WDAC bypass 為主要路徑
- [ ] 3-9. 修改 `services.py` `prepare_labeling_project()` lines 222–227：改用 ToolRegistry dispatch
- [ ] 3-10. 修改 `012_output.py`：新增 `_launch_tool(tool_id, file_path)` 統一入口
- [ ] 3-11. 修改 module_006：改讀 ToolRegistry；保留 `xany_dir` 作為 `executable_override`；保留 `legacy_mode` 欄位
- [ ] 3-12. 跑 `npm run test:python`，確認既有 module 行為不變

---

## Phase 4 — IntegrationProfile + ExternalSystemConnector

**注意：必須先完成 Phase 0 全部三項決策。**

- [ ] 4-1. 寫 ADR-A、ADR-B、ADR-C（參見 Phase 0）
- [ ] 4-2. 新增 `tests/annotation/test_integration_profile.py`（failing tests first）
- [ ] 4-3. 新增 `tests/annotation/test_connectors.py`（failing tests first）
- [ ] 4-4. 新增 `tests/annotation/test_tenant_isolation.py`（failing tests first）
- [ ] 4-5. 新增 `tests/annotation/test_sqlite_wal.py`（failing tests first）
- [ ] 4-6. 執行 DB migration（`sqlite_store.py` `connect()` 加 WAL；所有 6 張表加 `tenant_id`；新 `integration_profiles`, `jobs`, `audit_log` 表）
- [ ] 4-7. 建立 `annotation/integrations/contracts.py`（`ExternalSystemConnector` ABC, 所有 dataclass）
- [ ] 4-8. 建立 `annotation/integrations/profiles.py`（`IntegrationProfile` JSON loader + validator）
- [ ] 4-9. 建立 `annotation/integrations/mappings.py`（`FieldMapper`, `SchemaMapper`, `StatusMapper`）
- [ ] 4-10. 建立 `annotation/integrations/credential_store.py`（AES-256-GCM + OS keychain）
- [ ] 4-11. 建立 `annotation/integrations/connectors/fake_connector.py`（deterministic test fixture）
- [ ] 4-12. 建立 `annotation/integrations/connectors/file_connector.py`（local/UNC paths）
- [ ] 4-13. 修改 MCP tools：`annotation_create_dataset`, `annotation_ingest_assets`, `annotation_create_export` 加入可選新參數（backward compatible）
- [ ] 4-14. 跑 `npm run test:python`，確認既有所有 tests 全過

---

## Phase 5 — Orchestration Job API

- [ ] 5-1. 新增 `tests/annotation/test_job_service.py`（failing tests first，含 regression: `get_task` alias 保留）
- [ ] 5-2. 新增 `tests/annotation/test_audit_log.py`（failing tests first）
- [ ] 5-3. 修改 `sqlite_store.py`：新增 job CRUD（`create_job`, `update_job_state`, `get_job`）；`write_audit_log`（append-only）；`list_audit_log`；`list_dead_letter_jobs`
- [ ] 5-4. 修改 `services.py`：新增 `create_import_job`, `create_export_job`, `dry_run_export_job`, `get_job_status`, `cancel_job`, `get_conversion_report`, `list_dead_letter_jobs`, `retry_dead_letter_job`
- [ ] 5-5. 修改 `handlers.py`：
  - 替換 `get_job_status` stub（line 228）為真實查詢
  - 替換 `cancel_job` stub（line 230）為真實狀態轉換
  - 新增 `annotation_create_import_job`, `annotation_create_export_job`, `annotation_get_conversion_report`, `annotation_list_dead_letter_jobs`, `annotation_retry_job`
- [ ] 5-6. 確認 `get_task()` / `list_tasks()` alias 關係在 docstring 中文件化（不 rename）
- [ ] 5-7. 跑 `npm run test:python`，確認所有 tests 全過（包含 `test_get_task_still_returns_annotation_set`）
- [ ] 5-8. 更新 `docs/ANNOTATION_PLATFORM_ARCHITECTURE_DISCUSSION.html` Section 22 Sequence Diagrams（補 Credential + Schema Pin mini diagram）
