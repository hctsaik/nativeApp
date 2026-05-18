# Video Tracking Labeling (module_008)

## Why

標注影片中的物件目前需要人工逐幀標注，耗時且缺乏一致性。
平台已有圖片標注的 X-AnyLabeling 整合，但影片的時間軸傳播完全缺失。

使用者的實際工作流程：
1. 在某個關鍵幀選取物件（anchor frame）
2. 系統自動把 bounding box 傳播到前後 ±1 秒（可擴充）
3. 使用者審閱每一幀的結果，手動修正偏差較大的 frame
4. 從任一修正後的 frame 重新傳播（re-propagate）
5. 確認後匯出整個時間段的 X-AnyLabeling JSON

## What Changes

新增 `module_008 — 影片追蹤標注` 模組：

- Input：選擇影片、anchor frame、時間範圍；設定標注類別（共用 module_006 config）
- Process：
  - 影片拆幀（JPEG 快取）
  - DINOv2 特徵提取（.npy 快取）
  - 雙追蹤：0.5×Lucas-Kanade optical flow + 0.5×DINOv2 語意相似度
  - affine 變換（`estimateAffinePartial2D` + RANSAC），非 rigid translation
  - 長時間任務寫入 task.json，UI 用 st_autorefresh 輪詢
- Output：
  - 時間軸預覽（每幀縮圖 + bounding box 疊合）
  - 手動校正（點選 frame → 調整 bbox）
  - Re-propagation（從校正幀重新往前/後傳播）
  - 右鍵匯出整個時間段的 X-AnyLabeling JSON（相對路徑 imagePath）

## MVP Scope

**In scope：**
- 單一影片，單一 anchor frame
- Bounding box only，多個物件（multi-object）
- 預設 ±1 秒，可手動擴充範圍
- X-AnyLabeling JSON v6.0.0 匯出
- 信心分數（RANSAC inlier ratio）顯示於 UI
- DINO_AVAILABLE 降級（torch 缺失時退回 flow-only 模式）
- 長時間運算：subprocess worker + task.json 輪詢

**Out of scope for MVP：**
- Polygon 標注
- 多段時間軸選取
- 自動模型微調
- COCO / YOLO 匯出
- 多影片批次

## Decisions

- DINOv2（`facebook/dinov2-small`）直接整合，不做 OpenCV-only 過渡版
- 標注類別從 `{CIM_LOG_DIR}/config/module_006.json` 讀取（與 module_006 共用）
- 運算環境用獨立 `.venv-tracking`，比照 `.venv-xanylabeling` 模式
- 兩個 Streamlit 程序（Input / Output）透過 filesystem 溝通（session.json + task.json）
- 主要參考來源：專案內 `LabelMe_Dino/` codebase

## Success Criteria

- 給定影片 + anchor frame，系統在 ±1 秒範圍內自動追蹤並顯示 bounding box
- 使用者可手動校正任一幀，系統可從校正幀重新傳播
- 匯出的 X-AnyLabeling JSON 可用 X-AnyLabeling 開啟並顯示正確 bbox
- torch 未安裝時，系統降級到 flow-only 並顯示提示
- 長時間傳播期間 UI 顯示進度，不 block

## References

- `LabelMe_Dino/src/propagator.py` — 雙追蹤核心
- `LabelMe_Dino/src/dino_engine.py` — DINOv2-small 特徵
- `LabelMe_Dino/src/video_core.py` — 拆幀 + 快取
- `LabelMe_Dino/src/label_bridge.py` — X-AnyLabeling JSON 讀寫
- `sidecar/python-engine/scripts/module_006/_config.py` — 標注類別 config
- `docs/ANNOTATION_XANYLABELING.md` — x-anylabeling 打包模式
