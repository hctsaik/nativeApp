# Module 008：影片追蹤標注

> **開發者參考**：`scripts/module_008/README.md`
> **使用者操作指南**：`scripts/module_008/guide.html`（嵌入於 Input 頁面「📖 使用說明」）

---

## 概要

| 項目 | 值 |
|---|---|
| **plugin_id** | `module_008` |
| **版本** | 0.1.0 |
| **runner** | cv_framework |
| **標注格式** | X-AnyLabeling JSON v6.0.0 |
| **設定檔** | `{CIM_LOG_DIR}/config/module_008.json`（獨立，不共用 module_006）|

選取影片中的關鍵幀（anchor frame），在 X-AnyLabeling 畫好 bounding box 後，系統自動把 bbox 傳播到前後指定時間範圍（預設 ±1 秒），並允許使用者手動校正後重新傳播。

---

## 工作流程

```
Input 頁面
  ① 選擇影片檔（MP4/AVI/MOV），支援 📂 瀏覽 對話框
  ② 拖拉 slider 選擇 anchor frame
  ③ 點「🖊 在 X-AnyLabeling 畫框」→ X-AnyLabeling autosave → autorefresh 讀回 JSON
  ④ 設定追蹤時間範圍（before_sec / after_sec，預設 1.0 秒）
  ⑤ 點上方「▶ 執行」→ execute_logic() 呼叫 start_propagation() 啟動 subprocess worker

Output 頁面（自動輪詢 task.json，每 1.5 秒更新）
  ① 追蹤進度列（state / progress / dino_available）
  ② 時間軸縮圖列（anchor★，信心分數 🟢🟡🔴）
  ③ 點選幀 → 大圖 + PIL bbox 疊合 + 手動校正 UI
  ④ 「✅ 確認校正」→ save_correction()
  ⑤ 「🔄 從此幀重新傳播」→ re_propagate()
  ⑥ 「📤 匯出整個時間段（X-AnyLabeling JSON）」→ export_xanylabeling()
```

---

## 追蹤架構

雙追蹤策略（繼承自 LabelMe_Dino 專案）：

| 策略 | 技術 | 說明 |
|---|---|---|
| Lucas-Kanade Optical Flow | OpenCV `calcOpticalFlowPyrLK` | 9 點網格追蹤，median displacement，rigid 平移 |
| DINOv2 語意相似度 | `facebook/dinov2-small` | center-patch cosine similarity 作為信心校驗 |
| **合成信心分數** | — | `0.5 × optical_flow_conf + 0.5 × dino_conf` |
| DINO_AVAILABLE 降級 | — | torch 未安裝時自動退回 flow-only 模式，UI 顯示 warning |

---

## 工作區結構

```text
{CIM_LOG_DIR}/video-tracking/{session_id}/
  session.json         # 影片路徑、anchor、時間範圍、labels、anchor_bboxes
  task.json            # worker 寫入進度（state/progress/current_frame/total_frames/dino_available）
  frames/              # 拆出的 JPEG：frame_{idx:06d}.jpg
  features/            # DINOv2 特徵：frame_{idx:06d}.npy（torch 可用時）
  annotations/         # 每幀 bbox：frame_{idx:06d}.json（X-AnyLabeling JSON v6.0.0）
  anchor_labels/       # X-AnyLabeling 畫 anchor frame 的輸出 JSON
  exports/
    xanylabeling/      # 匯出的完整 JSON 集 + manifest.json
```

---

## Annotation JSON 格式

```json
{
  "version": "6.0.0",
  "imagePath": "../frames/frame_000042.jpg",
  "imageHeight": 720,
  "imageWidth": 1280,
  "imageData": null,
  "flags": {},
  "shapes": [
    {
      "label": "眼睛",
      "shape_type": "rectangle",
      "points": [[100.0, 80.0], [150.0, 120.0]],
      "description": "confidence=0.872",
      "flags": {},
      "group_id": null,
      "other_data": {}
    }
  ]
}
```

`imagePath` 使用相對路徑（可直接用 X-AnyLabeling 開啟）。  
`description` 欄位儲存信心分數（手動校正的幀固定為 `confidence=1.000`）。

---

## execute_logic() 行為

```
params（來自 render_input）:
  mode            = "tracking" | "idle"
  video_path      = str
  anchor_frame_idx = int
  session_dir     = str
  before_sec      = float
  after_sec       = float
  anchor_bboxes   = list[dict]   ← 必須非空才會啟動追蹤
  meta            = dict         ← fps, width, height, total_frames
  labels          = list[str]

行為:
  若 mode != "tracking" → 直接回傳 params
  若 anchor_bboxes 為空 → 回傳 {**params, "error": "..."}
  否則 → 呼叫 start_propagation(session_dir, session_data) → 回傳 params
```

---

## 設定系統（_config.py）

設定檔路徑：`{CIM_LOG_DIR}/config/module_008.json`（獨立，不依賴 module_006）

```json
{
  "annotation_labels": ["眼睛", "鼻子", "嘴巴"]
}
```

函式：
- `get_annotation_labels() → list[str]`
- `set_annotation_labels(labels: list[str]) → None`

---

## 檔案結構

```text
sidecar/python-engine/scripts/module_008/
  plugin.yaml              # runner: cv_framework, version: 0.1.0
  _config.py               # 獨立設定，讀 module_008.json
  _worker.py               # subprocess worker；propagation + task.json 更新
  008_input.py             # Streamlit Input 頁面
  008_process.py           # 無 Streamlit；execute_logic/start_propagation/…
  008_output.py            # Streamlit Output 頁面
  008_process_test.py      # 14 項測試（pytest）
  README.md                # 開發者快速參考
  guide.html               # 使用者操作指南（嵌入於 Input 頁）
```

---

## 長時間運算模式

`start_propagation()` → `subprocess.Popen(_worker.py)` → 不 block UI  
Worker 每完成一幀更新 `task.json`  
Output 頁面用 `st_autorefresh(interval=1500)` 輪詢

---

## 打包注意

DINOv2 需要 torch，建議使用獨立 `.venv-tracking`（比照 `.venv-xanylabeling`）：

```powershell
python -m uv venv --python 3.12 .venv-tracking
python -m uv pip install --python .venv-tracking\Scripts\python.exe `
    torch torchvision --index-url https://download.pytorch.org/whl/cpu
python -m uv pip install --python .venv-tracking\Scripts\python.exe `
    opencv-python-headless transformers pillow numpy
```

---

## 測試

```bash
pytest scripts/module_008/008_process_test.py -v
# 14 tests expected
```
