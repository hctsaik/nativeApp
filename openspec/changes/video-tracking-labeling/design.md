# Video Tracking Labeling — Design

## Module Identity

```text
id:          module_008
name:        影片追蹤標注
engine:      python-sidecar (Streamlit)
db enabled:  true (Portal 可見)
```

## File Layout

```text
sidecar/python-engine/scripts/module_008/
  plugin.yaml
  008_input.py        # Streamlit Input 頁面
  008_process.py      # 無 Streamlit；純邏輯
  008_output.py       # Streamlit Output 頁面
  008_process_test.py
  _config.py          # 讀 module_006.json 的 thin wrapper（re-export）
  _worker.py          # subprocess worker；只做 propagation + task.json 更新
```

工作目錄（runtime）：

```text
{CIM_LOG_DIR}/video-tracking/{session_id}/
  session.json         # anchor frame, video_path, time_range, labels, state
  task.json            # propagation 進度（worker 寫，UI 讀）
  frames/              # 拆出的 JPEG，{frame_idx:06d}.jpg
  features/            # DINOv2 特徵，{frame_idx:06d}.npy
  annotations/         # 每幀 bbox，{frame_idx:06d}.json  (LabelMe v6.0.0 格式)
  exports/
    labelme/           # 匯出的完整 JSON 集
```

## Tracking Architecture

```text
Input signal
  └── anchor bbox(es) on anchor_frame_idx
        │
        ├── Lucas-Kanade optical flow  (cv2.calcOpticalFlowPyrLK)
        │     translates bbox corner points
        │
        └── DINOv2 patch similarity  (facebook/dinov2-small)
              RANSAC affine (estimateAffinePartial2D, not rigid translation)
              inlier_ratio → confidence score
        │
        ▼
  weight = 0.5 × flow + 0.5 × dino
  final_bbox = weighted combination
  confidence = RANSAC inlier_ratio (stored in annotations JSON, shown in UI)
```

### DINO_AVAILABLE 降級

```python
try:
    import torch
    DINO_AVAILABLE = True
except ImportError:
    DINO_AVAILABLE = False
    # weight = 1.0 × flow only; UI shows 警告 banner
```

### 快取策略（解決 per-patch 3.6GB 問題）

- 只快取 anchor frame 鄰域（半徑 3 幀）的完整 patch feature grid
- 其他幀：僅快取 bbox ROI 區域（縮小 95%+ 記憶體）
- 快取 key：`{frame_idx}_{bbox_hash}.npy`

## Long-Running Task Pattern

比照現有 subprocess worker 模式：

```python
# 008_process.py — start_propagation()
worker_proc = subprocess.Popen(
    [sys.executable, "_worker.py", session_dir],
    cwd=module_dir,
)
```

`_worker.py` 每完成一幀就更新 `task.json`：

```json
{
  "state": "running",
  "progress": 0.45,
  "current_frame": 67,
  "total_frames": 120,
  "error": null
}
```

Output 頁面用 `st_autorefresh(interval=1500)` 輪詢 task.json。

## Anchor Frame BBox 輸入（比照 module_006 的 X-AnyLabeling 做法）

module_006 用 X-AnyLabeling 畫框、JSON 存結果、PIL 讀回顯示。
module_008 的 anchor frame bbox 走完全相同的流程：

```text
1. 使用者拖 anchor frame slider → 顯示影格預覽縮圖
2. 按「🖊 在 X-AnyLabeling 畫框」
   a. 從影片拆出 anchor frame → 存為 {session_dir}/anchor_frame.jpg
   b. 同步 classes.txt（從 module_006.json config 讀取）
   c. subprocess.Popen(xanylabeling --filename anchor_frame.jpg ...)
3. 使用者在 X-AnyLabeling 畫完 bbox 後存檔（autosave）
4. Input 頁面讀回 anchor_labels/anchor_frame.json（X-AnyLabeling JSON）
   → 從 shapes[] 取出所有 rectangle，作為 anchor_bboxes
5. 顯示 PIL 疊合預覽（同 module_006 的 _draw_annotations()）
6. 使用者設定時間範圍（before_sec / after_sec，預設 1.0）
7. 按「▶ 開始傳播」→ 寫 session.json，啟動 _worker subprocess
```

X-AnyLabeling 啟動指令（與 module_006 _launch_xany_single() 一致）：
```text
xanylabeling.exe
  --filename  {session_dir}/anchor_frame.jpg
  --output    {session_dir}/anchor_labels/
  --work-dir  {session_dir}/.xanylabeling
  --nodata --autosave --no-auto-update-check
  --labels    {session_dir}/classes.txt --validatelabel exact
```

## Session / Data Flow

```text
Input Page (008_input.py)
  1. 使用者選影片檔 + anchor frame（slider）
  2. 按「🖊 在 X-AnyLabeling 畫框」→ 拆幀 + 啟動 X-AnyLabeling
  3. st_autorefresh 偵測 anchor_labels/*.json 出現 → 顯示 PIL 預覽
  4. 使用者設定時間範圍（before_sec / after_sec，預設 1.0）
  5. 確認 anchor bbox 正確後，按「▶ 開始傳播」
  6. 寫 session.json → call process.start_propagation()

Output Page (008_output.py)
  1. 讀 session.json
  2. 如果 task.json.state == "running" → 顯示 progress bar + st_autorefresh
  3. 如果 task.json.state == "done" → 顯示時間軸縮圖 grid
  4. 點選 frame → 顯示大圖 + bbox 疊合 + 手動校正 UI
  5. 「從此幀重新傳播」→ call process.re_propagate(from_frame_idx)
  6. 「📤 匯出全部 JSON」→ 寫 exports/xanylabeling/
```

## session.json Schema

```json
{
  "session_id": "abc123",
  "video_path": "/abs/path/to/video.mp4",
  "anchor_frame_idx": 42,
  "fps": 30.0,
  "time_range_sec": [-1.0, 1.0],
  "labels": ["眼睛", "鼻子", "嘴巴"],
  "anchor_bboxes": [
    {"label": "眼睛", "x": 100, "y": 80, "w": 50, "h": 40}
  ],
  "state": "done"
}
```

## annotations/{frame_idx}.json Schema（X-AnyLabeling JSON）

```json
{
  "version": "6.0.0",
  "imagePath": "frames/000042.jpg",
  "imageHeight": 720,
  "imageWidth": 1280,
  "shapes": [
    {
      "label": "眼睛",
      "shape_type": "rectangle",
      "points": [[100, 80], [150, 120]],
      "description": "confidence=0.87"
    }
  ]
}
```

`imagePath` 使用相對路徑（相對於 session_dir）。
格式與 X-AnyLabeling autosave 輸出相同，可直接用 X-AnyLabeling 開啟。

## Output UI Layout

```
[進度條 / 完成狀態]

時間軸：[← 前一秒] ──── anchor ──── [後一秒 →]
縮圖列：[幀0] [幀1] ... [anchor★] ... [幀N]
                ↑ 點選進入校正模式

[大圖預覽 + bbox 疊合]
  [標籤選擇] [x][y][w][h] 數值微調
  [✅ 確認校正] [🔄 從此幀重新傳播]

[右側 panel]
  信心分數列表（每幀顏色標示：綠/黃/紅）

[底部]
  [📤 匯出整個時間段（X-AnyLabeling JSON）]
```

## plugin.yaml

```yaml
id: module_008
name: 影片追蹤標注
description: 選取影片關鍵幀標注物件，自動追蹤前後時間段並匯出 X-AnyLabeling JSON
category: 標注工具
version: 0.1.0
engine: python-sidecar
enabled: true
```

## .venv-tracking 安裝

比照 `.venv-xanylabeling`：

```powershell
python -m uv venv --python 3.12 .venv-tracking
python -m uv pip install --python .venv-tracking\Scripts\python.exe `
    torch torchvision --index-url https://download.pytorch.org/whl/cpu
python -m uv pip install --python .venv-tracking\Scripts\python.exe `
    opencv-python-headless transformers pillow numpy
```

開發階段可用現有 venv，PyInstaller 打包時切換至 `.venv-tracking`。

## Key Agent Discussion Decisions

| 議題 | 決策 |
|------|------|
| Optical flow 變換模型 | `estimateAffinePartial2D` (affine + RANSAC)，非 rigid translation |
| 信心指標 | RANSAC inlier_ratio，顯示於每幀 |
| 記憶體 | 只快取 anchor 鄰域完整 grid，其他幀僅快取 bbox ROI |
| 長時間運算 | subprocess worker + task.json + st_autorefresh(1500ms) |
| 降級策略 | DINO_AVAILABLE flag；無 torch 時退回 flow-only |
| 標注類別 | 讀 `{CIM_LOG_DIR}/config/module_006.json`，跨 Input/Output 共用 |
| DINOv2 版本 | `facebook/dinov2-small`（同 LabelMe_Dino codebase） |
| 匯出格式 | LabelMe JSON v6.0.0，imagePath 相對路徑 |
| 打包 | `.venv-tracking`，比照 `.venv-xanylabeling` |
| 時間範圍預設 | ±1 秒，使用者可調整 |
| v1 DINOv2 | 直接整合（不做 OpenCV-only 過渡版） |

## Not In MVP

- Polygon 標注
- 多 anchor frame / 多段時間軸
- COCO / YOLO 匯出
- 自動模型微調
- 多影片批次處理
- GPU 加速
