# 設計：X-AnyLabeling 動物影像 MCP 整合

## 核心定位

X-AnyLabeling 只作為標註前台與外部標註引擎。`animal-labeling-mcp` 提供穩定 domain API，管理資料、任務、標註狀態、預標註、QA 與匯出。

```
Claude / MCP Client
        │
        ▼
animal-labeling-mcp
        │
        ▼
Application Services
        │
        ├── Domain Model
        ├── Annotation Storage
        ├── Dataset Storage
        ├── XAnyLabelingAdapter
        ├── ModelPrelabelAdapter
        └── ExportAdapter
```

現有 `cim-gui-mcp` 可保留作 UI/E2E 驗證工具，但不得成為標註流程的主要控制面。

---

## Domain Model

```python
Dataset:
    id: str
    name: str
    root_uri: str
    state: DatasetState
    label_schema_id: str | None
    image_count: int
    metadata: dict

ImageAsset:
    id: str
    dataset_id: str
    uri: str
    checksum: str
    width: int
    height: int
    captured_at: str | None
    state: ImageState
    metadata: dict

LabelSchema:
    id: str
    name: str
    version: str
    annotation_types: list[str]  # bbox, polygon, classification, keypoint
    labels: list[LabelDef]

AnnotationSet:
    id: str
    dataset_id: str
    image_id: str | None
    source: str                 # human, ai, imported
    format: str                 # canonical, labelme, coco, yolo
    version: int
    state: AnnotationState

Annotation:
    id: str
    image_id: str
    label: str
    geometry: Geometry
    source: str                 # ai | human | imported
    confidence: float | None
    model_name: str | None
    model_version: str | None
    annotator_id: str | None
    review_status: str
    attributes: dict
    version: int

Geometry:
    type: str                   # bbox | polygon | point | mask | classification
    points: list

LabelingJob:
    id: str
    dataset_id: str
    task_id: str | None
    tool: str                   # x-anylabeling, model, exporter
    state: JobState
    total: int
    succeeded: int
    failed: int
    artifact_refs: list[str]
```

Domain model 不儲存 X-AnyLabeling 私有欄位作為主 contract。X-AnyLabeling 原始 payload 可放在 artifact 或 `external_payload`，但 application service 應使用 canonical model。

---

## Artifact Layout

```text
workspace/
  datasets/{dataset_id}/
    images/
    catalog.sqlite
    manifests/
      dataset-manifest.json
    annotations/
      {annotation_set_id}/
        canonical.json
        manifest.json
    external/
      x-anylabeling/{job_id}/
        project/
        exports/
    exports/
      coco/{export_id}/
      yolo-detect/{export_id}/
      yolo-seg/{export_id}/
```

`manifest.json` 應記錄：

- `domain_schema_version`
- `adapter_version`
- `x_anylabeling_version`
- `label_schema_id`
- `source_annotation_set_id`
- checksums
- generated_at

---

## Format Strategy

| Format | 用途 | 是否 canonical |
|--------|------|----------------|
| LabelMe / X-AnyLabeling JSON | 人工編輯與 round-trip | 否 |
| COCO | 治理、統計、評估、多任務表達 | 可作治理輸出 |
| YOLO Detection | 訓練輸出 | 否 |
| YOLO Segmentation | 訓練輸出 | 否 |
| Canonical JSON | 系統內部穩定格式 | 是 |

MVP 先支援 bbox、polygon、image classification。Keypoint 放 MVP+，因為 animal skeleton schema 需獨立版本化。

---

## MCP Resources

```text
animal://datasets/{dataset_id}
animal://datasets/{dataset_id}/images/{image_id}
animal://label-schemas/{schema_id}
animal://tasks/{task_id}
animal://annotations/{annotation_set_id}
animal://jobs/{job_id}
animal://exports/{export_id}
animal://reports/{report_id}
```

Resources 回傳 metadata 與 artifact URI，不直接回傳大型影像 bytes。

---

## MCP Tools

### Dataset

#### `animal_create_dataset`

```json
{
  "name": "farm-cam-2026-05",
  "source_uri": "file:///data/farm/cam01",
  "species_hint": ["cattle"],
  "metadata": {
    "site": "farm-a",
    "camera_id": "cam01"
  }
}
```

回傳 `Dataset`。

#### `animal_list_datasets`

查詢 dataset 清單，支援 state/filter。

#### `animal_ingest_images`

建立非同步 job，掃描影像、擷取尺寸/checksum/metadata，可選去重。

```json
{
  "dataset_id": "ds_001",
  "source_uri": "file:///data/farm/cam01",
  "deduplicate": true,
  "extract_metadata": true
}
```

### Label Schema

#### `animal_create_label_schema`

```json
{
  "name": "animal_detection_v1",
  "annotation_types": ["bbox", "polygon"],
  "labels": [
    {"name": "cat", "color": "#ff7f50"},
    {"name": "dog", "color": "#9370db"},
    {"name": "bird", "color": "#00a6a6"}
  ]
}
```

### Task / Workflow

#### `animal_create_annotation_task`

```json
{
  "dataset_id": "ds_001",
  "label_schema_id": "schema_001",
  "task_type": "object_detection",
  "annotation_type": "bbox",
  "assignee": "annotator_a"
}
```

#### `animal_open_xanylabeling_project`

開啟或準備 X-AnyLabeling project。此 tool 可啟動 GUI，但不控制 GUI。

```json
{
  "task_id": "task_001",
  "image_ids": ["img_001", "img_002"],
  "open_gui": true
}
```

### Pre-label

#### `animal_run_auto_label`

```json
{
  "task_id": "task_001",
  "model_profile": "animal-yolo-v1",
  "confidence_threshold": 0.35,
  "target_image_ids": ["img_001"],
  "write_mode": "draft"
}
```

`write_mode`：

- `draft`：寫入 AI 草稿，不覆蓋人工標註。
- `append`：附加新 AI 標註。
- `replace_ai`：只替換既有 AI 標註。
- `replace_all`：需 admin 權限，MVP 不開放。

### Annotation

#### `animal_get_image_annotations`

依 image 或 annotation set 讀取 canonical annotation。

#### `animal_upsert_annotations`

```json
{
  "image_id": "img_001",
  "base_version": 3,
  "annotations": [
    {
      "label": "dog",
      "type": "bbox",
      "points": [[120, 88], [420, 360]],
      "confidence": 0.91,
      "source": "human"
    }
  ]
}
```

必須檢查 `base_version`，避免覆蓋其他標註者或審核結果。

#### `animal_import_xanylabeling_annotations`

從 X-AnyLabeling/LabelMe JSON 匯入人工修正結果，產生新的 `AnnotationSet`。

### QA / Review

#### `animal_validate_annotations`

檢查：

- label 不在 schema
- bbox/polygon/keypoint 越界
- 空 annotation
- bbox 面積過小/過大
- polygon 自交
- required attributes 缺失
- version conflict

#### `animal_submit_for_review`

將 task/annotation set 送審。

#### `animal_review_task`

```json
{
  "task_id": "task_001",
  "decision": "approved",
  "comment": "bbox quality acceptable"
}
```

### Export

#### `animal_export_dataset`

```json
{
  "dataset_id": "ds_001",
  "format": "coco",
  "include_states": ["approved"],
  "output_uri": "file:///exports/farm-cam-coco-v1"
}
```

MVP 支援 `labelme`、`coco`、`yolo-detect`、`yolo-seg`。

### Jobs

#### `animal_get_job_status`

回傳：

```json
{
  "job_id": "job_001",
  "state": "partially_succeeded",
  "total": 1000,
  "succeeded": 972,
  "failed": 28,
  "failures_uri": "animal://jobs/job_001/failures"
}
```

---

## State Machines

### Dataset

```text
created -> ingesting -> ready -> active -> archived
                    └-> failed
```

### Image

```text
registered -> metadata_extracted -> ready
ready -> auto_label_pending -> auto_labeled
auto_labeled -> human_labeled -> reviewed -> approved -> exported
reviewed -> rejected -> human_labeled
```

### Annotation

```text
draft_ai -> human_modified -> submitted -> approved
submitted -> rejected -> human_modified
approved -> deprecated
```

### Task

```text
created -> assigned -> auto_labeling -> auto_labeled -> labeling
labeling -> submitted -> reviewing -> approved -> exported -> closed
reviewing -> rejected -> rework -> labeling
```

### Job

```text
queued -> running -> succeeded
running -> partially_succeeded
running -> failed
queued/running -> canceled
```

Rules:

- `approved` annotation 不可被一般 auto-label 覆蓋。
- 所有 annotation update 產生新 version。
- `source` 必須保留 `ai` / `human` / `imported`。
- Export 預設只包含 `approved`。
- Rejected task 必須回到 `rework`，不可直接 export。

---

## Error Contract

```json
{
  "ok": false,
  "error": {
    "code": "CONFLICT",
    "message": "Annotation version conflict.",
    "details": {
      "image_id": "img_001",
      "expected_version": 3,
      "actual_version": 4
    },
    "retryable": false
  }
}
```

Error codes:

- `VALIDATION_ERROR`
- `NOT_FOUND`
- `CONFLICT`
- `PERMISSION_DENIED`
- `MODEL_UNAVAILABLE`
- `INFERENCE_FAILED`
- `EXPORT_FAILED`
- `UNSUPPORTED_FORMAT`
- `RESOURCE_UNREADABLE`
- `PARTIAL_SUCCESS`

---

## Security

MVP 至少要求：

- Tool-level 權限：read、write、review、export、admin。
- Dataset/source path 白名單。
- 修改、審核、匯出皆寫入 audit log。
- 不信任影像 metadata、檔名、label description，不將其作 prompt/system instruction。
- `replace_all`、export、review approval 屬高風險操作，需要權限。

---

## Testing Strategy

| 層級 | 測試 |
|------|------|
| Domain unit | geometry、state transition、schema validation、version conflict |
| Adapter contract | X-AnyLabeling/LabelMe fixture import/export |
| Storage | SQLite migration、manifest、checksum、idempotent ingest |
| CLI | temp workspace import/export/validate |
| MCP | mock application service，驗證 tool input/output schema |
| GUI smoke | 少量確認能 open X-AnyLabeling project，不做 GUI flow control |

---

## MVP Acceptance

- 可建立 dataset，並匯入至少 100 張影像。
- 可建立 label schema 與 annotation task。
- 可啟動 auto-label job，產出 X-AnyLabeling/LabelMe 相容草稿。
- 可從 X-AnyLabeling 匯入人工修正結果。
- Annotation 保存 `source`、`confidence`、`version`、`state`。
- 可執行 validation report。
- 任務可送審、核准、退回。
- 已核准資料可匯出 YOLO detection 或 COCO。
- 常見錯誤皆有結構化 error response。
- 不依賴 GUI 點擊、視窗座標或截圖判斷流程。

