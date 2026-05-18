# 變更：Portal Workspace 版面重新設計

## 為何需要此變更

現有 Portal 版面有以下問題：

1. **使用者要選「Streamlit Tool」或「Micro-Frontend」**：這是實作細節，使用者不在乎。對使用者來說，他選了一個「功能」，系統決定怎麼跑。
2. **全畫面 iframe 沒有互動脈絡**：使用者不知道現在在輸入階段還是輸出階段，也看不到輸入的預覽影像與輸出的處理結果同時出現。
3. **輸入與輸出混在同一個 iframe 裡**：Input、Process、Output 三層的職責分離只有在 Python 後端有意義，前端沒有對應的結構。

## 目標

重新設計 Portal 版面為 **三區 Workspace 模式**：

```
┌─────────────────────────────────────────────────────────┐
│  Top Bar：功能選擇 + 檔案選擇 + Start/Stop             │
├────────────────────────────┬────────────────────────────┤
│  Left Panel                │  Right Panel               │
│  [Input] [Output] ← tabs  │  Display Area              │
│                            │                            │
│  Input tab active：        │  Input tab：選取影像預覽   │
│    Streamlit input iframe  │  Output tab：處理後影像    │
│    或 React micro-frontend │          + 輔助資料        │
│                            │                            │
│  Output tab active：       │                            │
│    Streamlit output iframe │                            │
│    或 React micro-frontend │                            │
└────────────────────────────┴────────────────────────────┘
```

## 範圍

**納入範圍：**
- 移除左側 sidebar 的 mode 切換（Streamlit / Micro-Frontend）
- Top Bar 維持：功能下拉、Choose File、Start/Stop 按鈕
- Bottom 分為左 Panel（含 Input/Output 頁籤）與右 Panel（Display）
- 新增 shared-protocol MessageTypes：`EXECUTE_START`、`EXECUTE_COMPLETE`、`DISPLAY_UPDATE`
- Portal 監聽 EXECUTE_START → 顯示 Loading → 收到 EXECUTE_COMPLETE → 自動切到 Output 頁籤
- Right Panel 顯示 DISPLAY_UPDATE 送來的影像（input 預覽或 output 結果）

**不納入範圍：**
- Python 工具的重寫（現有 `opencv_tool.py` 等暫不拆分，優先實作前端框架）
- 與 CV 模組框架（module_001 等）的完整整合（作為下一個 spec 的工作）
- RWD / 行動端版型
