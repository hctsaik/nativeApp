# Annotation Common Component and X-AnyLabeling Integration

Last updated: 2026-05-16 (module_006 UX redesign — Stepper + thumbnail grid + 3-agent review)

This document summarizes the current implementation state for the platform annotation common component and the X-AnyLabeling integration.

## Current Status

The MVP is implemented and validated for:

- Platform-owned canonical annotation data.
- Image assets.
- BBox annotations.
- Polygon annotations.
- Image-level classification in the core model.
- Label schema and attribute schema validation.
- Basic review and approval.
- Local workspace storage with SQLite metadata.
- Artifact files with checksums.
- LabelMe / X-AnyLabeling-compatible JSON import/export.
- Native ISAT JSON import/export.
- X-AnyLabeling project folder preparation.
- ISAT project folder preparation.
- X-AnyLabeling runtime detection.
- Optional X-AnyLabeling GUI launch handoff.
- COCO import/export.
- YOLO detection import/export.
- YOLO segmentation import/export.
- Conversion reports and export manifests.
- Electron visual workflow demo through `module_008`.
- Generic `annotation_*` MCP server package.
- X-AnyLabeling integration in `module_006` animal tagger (Phase 1 prepare / Phase 2 import).
- module_006 UX redesign: Stepper navigation, thumbnail grid, side-by-side image comparison.
- Contrast enhancement (annotation result only, preserves original).
- Live sync polling (Phase 1 output auto-refreshes every 8 s).
- Inline import ("立即匯入") with confirmation and format selector.
- Single-image X-AnyLabeling launch from browse mode ("🖊 標注工具").
- Chinese label rendering fix (CJK font fallback: msyh.ttc → msjh.ttc → mingliu.ttc).
- 4-point rectangle bbox fix for X-AnyLabeling import (min/max over all points).
- Browse mode reads labels_dir from session.json; X-Any annotations visible without Phase 2.

The current design keeps `annotation-core` as the only canonical source of truth. X-AnyLabeling, LabelMe, ISAT, COCO, and YOLO files are adapter inputs or derived artifacts.

## Installed X-AnyLabeling Runtime

X-AnyLabeling is installed in a repo-local virtual environment:

```text
C:\code\claude\nativeApp\.venv-xanylabeling
```

The installed command is:

```text
C:\code\claude\nativeApp\.venv-xanylabeling\Scripts\xanylabeling.exe
```

Verified version:

```text
4.0.0-beta.7
```

Verified Python runtime:

```text
Python 3.11.9
```

Verified command:

```powershell
py -3.11 -c "import sys; sys.path.insert(0, r'.venv-xanylabeling\Lib\site-packages'); from anylabeling.app import main; sys.argv=['xanylabeling','checks']; main()"
```

The project detects X-AnyLabeling in this order:

1. `XANYLABELING_EXE`
2. `.venv-xanylabeling\Scripts\xanylabeling.exe`
3. `PATH`

## Installation Notes

The installed runtime follows the official X-AnyLabeling quick-start guidance for a CPU environment, with Python 3.11 on this machine so WDAC can route launch through the trusted Windows Python Launcher:

```powershell
python -m pip install -U uv
python -m uv venv --python 3.11 .venv-xanylabeling
python -m uv pip install --python .venv-xanylabeling\Scripts\python.exe --pre "x-anylabeling-cvhub[cpu]"
py -3.11 -c "import sys; sys.path.insert(0, r'.venv-xanylabeling\Lib\site-packages'); from anylabeling.app import main; sys.argv=['xanylabeling','checks']; main()"
```

The repo root `.gitignore` excludes `.venv-xanylabeling/`.

## Main Code Locations

```text
sidecar/python-engine/annotation/
  core/
    models.py
    states.py
    validation.py
    errors.py
  storage/
    ports.py
    artifacts.py
    sqlite_store.py
    workspace.py
  adapters/
    labelme.py
    isat.py
    labeling_runtime.py
    xanylabeling.py
    xanylabeling_runtime.py
    coco.py
    yolo_detection.py
    yolo_segmentation.py
  domains/
    animal/schema_presets.py
  services.py

sidecar/python-engine/scripts/module_006/
  006_input.py       (三模式：瀏覽標記 / Phase 1 / Phase 2)
  006_process.py     (xany_phase1、xany_phase2、browse dispatcher)
  006_output.py
  006_process_test.py
  _config.py         (annotation_labels 持久化 config)
  plugin.yaml

sidecar/python-engine/scripts/module_008/
  008_input.py       (影片選擇 / anchor frame / X-AnyLabeling 畫框 / 啟動傳播)
  008_process.py     (start_propagation / re_propagate / save_correction / export)
  008_output.py      (時間軸縮圖列 / 校正 UI / 匯出)
  008_process_test.py
  _config.py         (re-export module_006 annotation_labels)
  _worker.py         (subprocess propagation worker; DINOv2 + optical flow)
  plugin.yaml

mcp/annotation_mcp/
  server.py
  handlers.py
  config.py
```

## Electron Workflow

The visual workflow is exposed as:

```text
008 - Annotation Common Component Demo
```

Despite the historical "Demo" suffix, the module now supports the MVP workflow:

1. Create dataset/schema.
2. Select generated sample, host-selected image, extra images, or image folders.
3. Create canonical annotation set.
4. Prepare a LabelMe/X-AnyLabeling/ISAT project folder.
5. Optionally launch the selected labeling tool.
6. Optionally import reviewed LabelMe/X-AnyLabeling/ISAT/COCO/YOLO labels.
7. Validate.
8. Submit and approve.
9. Export LabelMe, X-AnyLabeling, ISAT, COCO, YOLO detection, or YOLO segmentation artifacts.
10. Show visual preview and export content in Output.

Default project output:

```text
C:\code\claude\nativeApp\tmp\annotation-visual-demo-electron
```

Typical generated layout:

```text
xany_project/
  images/
  labels/
  classes.txt
  manifest.json

exports/
  labelme/
    <asset_id>.json
    manifest.json
    conversion_report.json
  coco/
    annotations.json
    manifest.json
    conversion_report.json
  yolo/
    labels/
    classes.txt
    manifest.json
    conversion_report.json

workspace/
  catalog.sqlite
  datasets/
```

## X-AnyLabeling Launch Handoff

When the user enables "Open in X-AnyLabeling after project creation", the platform launches:

```text
xanylabeling --filename <project>\images --output <project>\labels --work-dir <project>\.xanylabeling --nodata --autosave --no-auto-update-check --labels <project>\classes.txt --validatelabel exact
```

This is not GUI automation. It is a project/folder handoff to the X-AnyLabeling GUI.

## MCP Surface

The annotation MCP server is separate from `cim_gui_mcp`.

MCP package:

```text
mcp/annotation_mcp
```

Configured in:

```text
.mcp.json
```

Important tools:

```text
annotation_create_dataset
annotation_ingest_assets
annotation_create_schema
annotation_create_task
annotation_get_task
annotation_list_tasks
annotation_upsert_annotations
annotation_validate_set
annotation_submit_for_review
annotation_review_task
annotation_supported_annotation_formats
annotation_prepare_labeling_project
annotation_prepare_xanylabeling_project
annotation_detect_xanylabeling
annotation_launch_xanylabeling_project
annotation_detect_labeling_tool
annotation_launch_labeling_project
annotation_import_xanylabeling
annotation_import_annotations
annotation_import_project_labels
annotation_create_export
annotation_get_export
```

## Validation Results

Latest verified gates:

```text
sidecar/python-engine:
396 passed, 1 xpassed

mcp:
43 passed

openspec validate annotation-common-component --strict:
valid

openspec validate x-anylabeling-adapter-mvp --strict:
valid

xanylabeling checks:
passed
```

## OpenSpec Changes

Relevant OpenSpec changes:

```text
openspec/changes/annotation-common-component/
openspec/changes/x-anylabeling-adapter-mvp/
openspec/changes/multi-labeling-tool-format-support/
```

The old animal-specific draft remains:

```text
openspec/changes/x-anylabeling-animal-mcp/
```

That older draft should be treated as historical context. New implementation follows the common component split:

```text
annotation-core
annotation-adapters
annotation-domains
annotation-mcp
module_008 visual workflow
```

## Not In MVP

The following are intentionally not implemented yet:

- GUI automation inside X-AnyLabeling.
- Multi-user collaboration and locks.
- True async job queue.
- Full audit log.
- Mask editing and mask conversion.
- Keypoint/skeleton workflows.
- Tracking/video annotation (implemented in module_008).
- OCR layout editing.
- Production packaging of `.venv-xanylabeling`.

## module_006 Animal Tagger — X-AnyLabeling Integration

`module_006` has three steps navigated via a Stepper UI:

| 步驟 | 名稱 | 說明 |
|------|------|------|
| 1 | 瀏覽標記 | 縮圖格 + 右側詳細面板；支援類別 + 狀態雙篩選、X-Any 標注結果疊合、強化對比（僅標注結果）、✕重設分類 |
| 2 | 準備標注專案 | 從 DB 篩選圖片 → 建立 xany_project → 可啟動 X-AnyLabeling GUI |
| 3 | 匯入標注結果 | 匯入 labels/ → validate → approve → 匯出 COCO/YOLO（可選格式） |

步驟 3 在 `session.json` 不存在時顯示為 🔒 鎖定。

### Input 參數

**步驟 2（Phase 1）：**
- 篩選類別（ALL / 貓 / 狗 / 大象）
- 標注 Labels（逗號分隔，預設 貓, 狗, 大象）
- DB 路徑 / 影像目錄
- Workspace 根目錄（預設 `tmp/animal-annotation`）
- 自動啟動 X-AnyLabeling checkbox

**步驟 3（Phase 2）：**
- Workspace 根目錄（自動讀取 session.json；顯示建立日期，技術 ID 折疊隱藏）
- labels/ 路徑（自動填入）
- approve checkbox + export_formats multiselect

### Output 功能（Browse 模式）

| 功能 | 說明 |
|------|------|
| 縮圖格 | 選取後藍色邊框高亮；狀態 badge（⏳/📦/🏷/✅） |
| 雙篩選 | 類別（ALL/貓/狗/大象）+ 狀態各一個 selectbox |
| 詳細面板 | 分類選單（預選已儲存分類）+ ✅確認 + →跳過 + ✕重設 |
| 強化對比 | `🔆 強化對比（僅標注結果）` toggle；原圖不受影響 |
| 標注結果疊合 | PIL bbox/polygon 繪製；CJK font 支援中文標籤 |
| 🖊 標注工具 | 從縮圖列表直接開啟 X-AnyLabeling 對單圖標注 |
| 標注明細 | expander 預設展開，顯示 Label/Shape/Points |
| 狀態說明 | 📖 expander 說明四種狀態含意 |

### Output 功能（Phase 1 Live Sync）

- 每 8 秒自動更新標注進度（減少 CONNECTING 斷線頻率）
- 標注完成時顯示「⚡ 立即匯入並匯出」按鈕
- 點擊後顯示確認對話框 + 格式選擇器（coco / yolo-detection / labelme），確認後才執行

### session.json

持久化至 `{workspace_root}/session.json`：

```json
{
  "dataset_id": "ds_...",
  "schema_id": "schema_...",
  "xany_dir": "...",
  "labels_dir": "...",
  "labels": ["貓", "狗", "大象"]
}
```

匯出結果寫入 `{workspace_root}/exports/{coco|yolo_detection}/`。

Browse 模式讀取 `labels_dir` 並直接顯示標注框，**不需執行步驟 3** 即可在步驟 1 看到 X-AnyLabeling 標注結果。

### Test Coverage（10 tests, `006_process_test.py`）

| 測試 | 說明 |
|------|------|
| `test_browse_passthrough_with_valid_db` | browse 正常讀取 DB |
| `test_browse_returns_error_when_db_missing` | DB 不存在 → error |
| `test_phase1_creates_xany_project` | xany_project 結構正確 |
| `test_phase1_classes_txt_contains_labels` | classes.txt 包含所有 labels |
| `test_phase1_category_filter_reduces_images` | 類別篩選縮減圖片數 |
| `test_phase1_saves_session_json` | session.json 持久化 |
| `test_phase1_returns_error_when_db_missing` | DB 缺失 → error |
| `test_phase2_imports_and_exports` | import + COCO/YOLO 匯出 |
| `test_phase2_without_approve_stays_draft` | approve=False → state=draft |
| `test_no_streamlit_import_in_process` | process.py 無 streamlit import |

### Known Bugs Fixed

| Bug | 修正 |
|-----|------|
| X-AnyLabeling 4-point rectangle → height=0 validation fail | 改用 min/max 計算 bbox |
| CJK label 亂碼 | 依序嘗試 msyh.ttc / msjh.ttc / mingliu.ttc / simsun.ttc |
| 強化對比誤套用到原圖 | enhance 只傳入 `_draw_annotations()`，原圖 `st.image` 不套用 |

## Recommended Next Steps

1. Rename `module_008` display name from "Demo" to a production workflow name when product wording is settled.
2. Add export package/zip generation for COCO and YOLO outputs.
3. Add a migration strategy for existing `workspace/catalog.sqlite`.
4. Decide whether X-AnyLabeling runtime should be bundled, installed separately, or configured by `XANYLABELING_EXE` in production.
5. Add screenshots or Playwright visual assertions for the Electron annotation workflow.
6. Keyboard shortcuts for classification (number keys 1–4 = 貓/狗/大象/unknown, Enter = 確認, Space = 跳過).
7. Batch classification for same-category images.
8. "強化圖匯出" option in Phase 1: save contrast-enhanced versions to a separate dir for X-AnyLabeling annotation of hard-to-see defects.
