# Proposal: Unified Annotation Platform (module_009)

**狀態**：草稿  
**日期**：2026-05-16  
**作者**：system（CV 專家 × 架構師 × UX 專家 × User 四方討論後整合）

---

## 一、為什麼要做

### 現況問題

| 問題 | 現象 |
|---|---|
| 資料狀態不透明 | 研究員靠紙本記錄「哪些檔案標完了」 |
| 圖片與影片分開管理 | module_006 管圖片、module_008 管影片，兩套流程不能互通 |
| 無法多檔管理 | 每次只能處理一張圖或一支影片，沒有整體進度視野 |
| UX 流程模糊 | module_008 有兩個按鈕順序不明確，使用者不知從何開始 |
| 無 process lock | 可能同時對同一影片開多個 X-AnyLabeling 視窗造成資料衝突 |
| 追蹤結果難修正 | 單幀校正需要重開整支影片，容易誤改其他幀 |

### 機會

1. **影像與影片的標注單元相同**：都是「一幀 + 一組 bbox」，只需統一資料模型
2. **X-AnyLabeling 已整合**：MCP tools 已封裝啟動邏輯，可直接複用
3. **DINOv2 + LK 已實作**：module_008 的追蹤核心可移植為背景預處理 job，讓用戶得到「自動草稿」而非空白畫布

---

## 二、我們要做什麼

建立 **module_009：統一標注平台（Unified Annotation Platform）**，一個同時兼顧影像資料集與影片的標注管理系統。

### 核心功能

1. **標注總表（Annotation Master Table）**  
   顯示資料夾內所有影片與圖片的標注進度，支援篩選、搜尋、狀態追蹤

2. **一鍵啟動標注（X-AnyLabeling 整合）**  
   點擊「🛠️ 開啟標注」→ 背景跑 DINOv2+LK 產出初始 bbox → X-AnyLabeling 帶入草稿開啟  
   Process lock 防止同一檔案被重複開啟

3. **單幀校正（Single Frame Correction）**  
   從總表選一幀，只開那一幀的 X-AnyLabeling，修正後自動回寫

4. **DB 同步（Annotation Archive）**  
   確認無誤後，一鍵將標注結果歸檔至 SQLite，顯示確認提示（「將存入 N 筆結果」）

5. **自動跳下一筆**  
   完成一個檔案後，自動聚焦到下一個未標記項目

---

## 三、設計決策記錄

| 決策 | 選擇 | 理由 |
|---|---|---|
| Module ID | `module_009` | 保留 module_008，不混淆職責 |
| Runner | 新建 `annotation_runner.py` | cv_framework_runner 雙進程模型不支援即時 Master Table |
| 追蹤策略 | DINOv2+LK 作背景預處理 | 用戶等幾秒換省手工，X-AnyLabeling 開啟時已有草稿 |
| 影像/影片統一 | `(source_id, frame_idx)` 複合主鍵 | 圖片是 `frame_idx=0`，影片是 `frame_idx=N`，一張 DB 表涵蓋兩者 |
| Process lock | SQLite row + PID 驗證 | DB 是 single source of truth，不需額外 lock 檔案 |
| 術語 | 「存檔備份」而非「更新至 DB」 | 降低技術門檻，User 對「DB」感到緊張 |
| module_006 整合 | 共享 X-AnyLabeling project 格式 | 不直接呼叫 Python 函數，用共通 JSON 格式解耦 |

---

## 四、不在範圍內（Out of Scope）

- 多人協作標注（concurrent annotation by multiple users）
- 雲端儲存 / 遠端同步
- 標注品質審核工作流（review / approve）
- 即時影片串流標注
- module_008 的功能移植（module_008 繼續維持原樣）

---

## 五、成功標準

- [ ] 研究員能從資料夾一次載入多支影片 + 圖片，看到完整進度總表
- [ ] 點「開啟標注」後，X-AnyLabeling 開啟時已有 DINOv2 草稿 bbox（或 fallback 空白，無 crash）
- [ ] Process lock 正常運作：同一檔案無法重複開啟 X-AnyLabeling
- [ ] 單幀校正只開那一幀，不影響其他幀的標注資料
- [ ] 「存檔備份」前顯示確認提示，成功後本地暫存移至 backup/
- [ ] 完成一個檔案後，自動聚焦下一個未標記項目
- [ ] 全套 pytest 通過（process 層），不含 Streamlit
