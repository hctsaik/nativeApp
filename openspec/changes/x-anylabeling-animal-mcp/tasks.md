# Tasks：X-AnyLabeling 動物影像 MCP 整合規劃

## Phase 0 — 決策確認

- [ ] 確認 MVP 標註類型：bbox + polygon + image classification；keypoint 延後
- [ ] 確認 canonical format 採自定 JSON，LabelMe/X-AnyLabeling 只作 adapter
- [ ] 確認 X-AnyLabeling 版本支援範圍與安裝方式
- [ ] 確認動物 label schema 初版 taxonomy
- [ ] 確認 workspace root、資料路徑白名單與 artifact 保存策略

## Phase 1 — Domain Model

- [ ] 建立 `Dataset`、`ImageAsset`、`LabelSchema`、`AnnotationSet`、`Annotation`、`Geometry`、`LabelingJob` dataclass / schema
- [ ] 定義 state enum：Dataset、Image、Annotation、Task、Job
- [ ] 實作 geometry validation：bbox、polygon、classification
- [ ] 實作 annotation version conflict 檢查
- [ ] 建立 domain unit tests

## Phase 2 — Storage / Artifact Layout

- [ ] 建立 local catalog SQLite schema
- [ ] 建立 artifact workspace layout
- [ ] 實作 manifest writer / reader
- [ ] 實作 checksum 與 idempotent image ingest
- [ ] 建立 migration tests

## Phase 3 — X-AnyLabeling Adapter

- [ ] 定義 `XAnyLabelingProjectAdapter`
- [ ] 定義 `XAnyLabelingRuntimeAdapter`
- [ ] 實作 LabelMe/X-AnyLabeling JSON import
- [ ] 實作 LabelMe/X-AnyLabeling JSON export
- [ ] 實作 project folder preparation
- [ ] 實作 open project / launch GUI，僅啟動，不遙控 GUI
- [ ] 建立 adapter contract fixtures 與 round-trip tests

## Phase 4 — Application Services

- [ ] `create_dataset`
- [ ] `ingest_images`
- [ ] `create_label_schema`
- [ ] `create_annotation_task`
- [ ] `open_xanylabeling_project`
- [ ] `import_xanylabeling_annotations`
- [ ] `validate_annotations`
- [ ] `submit_for_review`
- [ ] `review_task`
- [ ] `export_dataset`
- [ ] `get_job_status`

## Phase 5 — MCP Server

- [ ] 建立 `mcp/animal_labeling_mcp/`
- [ ] 建立 MCP resources：
  - [ ] `animal://datasets/{dataset_id}`
  - [ ] `animal://datasets/{dataset_id}/images/{image_id}`
  - [ ] `animal://label-schemas/{schema_id}`
  - [ ] `animal://tasks/{task_id}`
  - [ ] `animal://annotations/{annotation_set_id}`
  - [ ] `animal://jobs/{job_id}`
  - [ ] `animal://exports/{export_id}`
- [ ] 建立 MCP tools：
  - [ ] `animal_create_dataset`
  - [ ] `animal_list_datasets`
  - [ ] `animal_ingest_images`
  - [ ] `animal_create_label_schema`
  - [ ] `animal_create_annotation_task`
  - [ ] `animal_open_xanylabeling_project`
  - [ ] `animal_run_auto_label`
  - [ ] `animal_get_image_annotations`
  - [ ] `animal_upsert_annotations`
  - [ ] `animal_import_xanylabeling_annotations`
  - [ ] `animal_validate_annotations`
  - [ ] `animal_submit_for_review`
  - [ ] `animal_review_task`
  - [ ] `animal_export_dataset`
  - [ ] `animal_get_job_status`
- [ ] 建立 MCP tool schema tests

## Phase 6 — Auto-label MVP

- [ ] 定義 model profile 格式
- [ ] 支援一個 YOLO detection model profile
- [ ] 支援 draft/append/replace_ai write mode
- [ ] 保存 `model_name`、`model_version`、`confidence`、`prelabel_run_id`
- [ ] 建立 low-confidence review queue
- [ ] 建立 partial success job report

## Phase 7 — Export / QA

- [ ] LabelMe export
- [ ] COCO export
- [ ] YOLO detection export
- [ ] YOLO segmentation export
- [ ] Validation report：unknown label、out of bounds、empty annotation、polygon self-intersection、required attributes
- [ ] Dataset stats：class distribution、checked/review rate、AI vs human modified rate

## Phase 8 — Documentation / Packaging

- [ ] 更新 `mcp/README.md` 或建立 `mcp/animal_labeling_mcp/README.md`
- [ ] 更新 `.mcp.json` 或 MCP install guidance
- [ ] 記錄 X-AnyLabeling 安裝與 capability detection
- [ ] 記錄 production logs：`mcp.log`、`xanylabeling.log`、`job-{id}.log`
- [ ] 打包策略：X-AnyLabeling 作外部 dependency bundle，不與核心 engine 強耦合

## 驗收條件

- [ ] 不依賴 GUI 點擊或視窗座標即可完成資料/標註/匯出流程
- [ ] 100 張影像 ingest + schema + task + validation + export 成功
- [ ] X-AnyLabeling 人工修正結果可 round-trip 回 canonical annotation
- [ ] Approved annotation 不會被 auto-label 覆蓋
- [ ] 所有修改型 tool 都有 version/conflict handling
- [ ] 所有長任務都有 job status 與 structured error

