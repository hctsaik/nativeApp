# Module 008 — 影片追蹤標注

> **完整技術文件**：[docs/modules/module_008.md](../../../../../docs/modules/module_008.md)
> **使用者操作指南**：[guide.html](guide.html)（嵌入於 Input 頁面「📖 使用說明」）

---

## 快速參考

### 檔案清單

| 檔案 | 用途 |
|---|---|
| `plugin.yaml` | 模組宣告（id: module_008, runner: cv_framework, version: 0.1.0）|
| `_config.py` | 獨立設定，讀寫 `{CIM_LOG_DIR}/config/module_008.json` |
| `_worker.py` | subprocess worker；DINOv2 + LK optical flow 追蹤，更新 `task.json` |
| `008_input.py` | Streamlit Input 頁面，`render_input() → dict` |
| `008_process.py` | 無 Streamlit；`execute_logic()` 觸發 `start_propagation()` |
| `008_output.py` | Streamlit Output 頁面，時間軸 + 校正 + 匯出 |
| `008_process_test.py` | 14 項 pytest 測試 |
| `guide.html` | 使用者操作指南（HTML，嵌入於 Input 頁）|

---

## render_input() 回傳合約

```python
{
    "mode": "tracking" | "idle",
    "video_path": str,
    "anchor_frame_idx": int,
    "session_dir": str,
    "before_sec": float,
    "after_sec": float,
    "anchor_bboxes": list[dict],   # 非空才能執行
    "meta": {                       # 影片元資料
        "fps": float,
        "width": int,
        "height": int,
        "total_frames": int
    },
    "labels": list[str]
}
```

## execute_logic() 行為

```
若 mode != "tracking"        → 直接回傳 params
若 anchor_bboxes 為空        → {**params, "error": "請先畫框..."}
否則                          → start_propagation() → 回傳 params
```

---

## 設定系統

設定檔：`{CIM_LOG_DIR}/config/module_008.json`（獨立，不共用 module_006）

```json
{ "annotation_labels": ["眼睛", "鼻子", "嘴巴"] }
```

```python
from _config import get_annotation_labels, set_annotation_labels
```

---

## 008_process.py 公開 API

```python
start_propagation(session_dir, session_data) → dict
re_propagate(session_dir, from_frame_idx) → dict
save_correction(session_dir, frame_idx, bboxes) → None
export_xanylabeling(session_dir) → dict
get_task_status(session_dir) → dict
load_session(session_dir) → dict | None
load_annotation(session_dir, frame_idx) → dict | None
list_annotated_frames(session_dir) → list[int]
get_xany_exe(project_root) → str
execute_logic(params) → dict   ← cv_framework_runner 呼叫點
```

---

## 工作區佈局

```
{CIM_LOG_DIR}/video-tracking/{session_id}/
  session.json    frames/    features/    annotations/
  anchor_labels/  task.json  exports/xanylabeling/
```

---

## 測試

```bash
cd sidecar/python-engine
pytest scripts/module_008/008_process_test.py -v
# 14 tests, 0 failures
```
