"""
_help.py — CIM 標注工作流平台「使用說明」FAB 按鈕 + Modal

用法（在每個 input/output py 的 render 函式最前面呼叫）：
    _help.render_help_button("module_010", "input")
"""
from __future__ import annotations

import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# 各模組說明內容（module_id + side → HTML 字串）
# ─────────────────────────────────────────────────────────────────────────────

_HELP_CONTENT: dict[str, str] = {

    # ── module_019 ────────────────────────────────────────────────────────────
    "module_019_input": """
<h3>🌐 Data Downloader — 使用說明</h3>
<p><strong>功能說明：</strong>從遠端 Service 下載資料集（ZIP 壓縮包），解壓後存放到本機，供後續 Data Feeder 使用。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>在「Service Base URL」欄位輸入後端服務的網址，例如 <code>http://api.internal:8080</code>。</li>
  <li>點擊「🔄 載入資料集清單」按鈕，系統會向 Service 查詢可用的資料集。</li>
  <li>從下拉選單選擇您要下載的資料集，右側會顯示該資料集的圖片張數。</li>
  <li>若本機已有下載紀錄，系統會顯示提示。如需重新下載最新版本，請勾選「重新下載」。</li>
  <li>確認設定後，點擊右上角的「▶ 執行」按鈕開始下載。</li>
</ol>

<h4>📝 欄位說明</h4>
<ul>
  <li><strong>Service Base URL（必填）</strong>：後端服務的根網址，不含路徑結尾斜線。</li>
  <li><strong>資料集（必填）</strong>：從 Service 取得的清單中選擇一個資料集。</li>
  <li><strong>重新下載（選填）</strong>：勾選後會覆蓋本機已有的資料，重新從 Service 下載。不勾選則直接使用本機快取。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>Service URL 變更後，資料集清單會自動清除，需重新載入。</li>
  <li>下載完成後，右側 Output 頁面會顯示每張圖片的標注狀態（未標注 / 需複核 / 已完成）。</li>
  <li>下載完成後系統會自動將資料夾路徑填入 Data Feeder，直接切換到第 2 個 Tab 即可。</li>
</ul>
""",

    "module_019_output": """
<h3>🌐 Data Downloader — 結果說明</h3>
<p><strong>功能說明：</strong>顯示資料集下載結果，包括圖片張數、各狀態統計，並引導您前往 Data Feeder 繼續作業。</p>

<h4>📊 結果頁面說明</h4>
<ul>
  <li><strong>四個統計指標</strong>：
    <ul>
      <li>🔢 總張數：本次下載的圖片總數。</li>
      <li>🔴 未標注：尚未有標注資料的圖片。</li>
      <li>🟡 需複核：已有標注但狀態標記為需要複核的圖片。</li>
      <li>🟢 已完成：標注已完成的圖片。</li>
    </ul>
  </li>
  <li><strong>命名衝突警告</strong>：若下載包中有同名 JSON 被覆蓋，會列出受影響的檔案名稱。通常可忽略。</li>
  <li><strong>下一步引導</strong>：顯示解壓後的本機資料夾路徑，可點擊「📋 複製路徑」複製到剪貼簿。</li>
</ul>

<h4>📋 圖片清單操作</h4>
<ol>
  <li>使用頂部的篩選按鈕（全部 / 未標注 / 需複核 / 已完成）過濾要查看的圖片。</li>
  <li>超過 50 張時會自動分頁，使用「← 上一頁」「下一頁 →」翻頁。</li>
</ol>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>下載中時，此頁面會每 0.8 秒自動刷新，顯示目前下載進度。</li>
  <li>若顯示錯誤，請確認 Service URL 正確，且網路連線正常。</li>
  <li>下載完成的資料夾路徑已自動填入 Data Feeder，直接切換到第 2 個 Tab 即可繼續。</li>
</ul>
""",

    # ── module_010 ────────────────────────────────────────────────────────────
    "module_010_input": """
<h3>📦 Data Feeder — 使用說明</h3>
<p><strong>功能說明：</strong>從資料夾、資料庫或 API 建立標準化圖片清單（DatasetManifest），作為整個標注流程的資料來源。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>選擇「資料來源類型」：📁 資料夾（最常用）、🗄️ 資料庫、或 🌐 API。</li>
  <li>根據選擇的類型填寫對應欄位（見下方欄位說明）。</li>
  <li>確認設定後，點擊「▶ 執行」建立 Manifest。</li>
  <li>右側 Output 頁面會顯示已掃描到的圖片數量與標注進度。</li>
</ol>

<h4>📝 欄位說明</h4>
<p><strong>📁 資料夾模式</strong></p>
<ul>
  <li><strong>資料夾路徑（必填）</strong>：圖片所在資料夾，可點擊「📂 瀏覽」選擇，或直接貼上路徑。</li>
  <li><strong>遞迴掃描子資料夾</strong>：勾選後會掃描資料夾內的所有子目錄。</li>
  <li><strong>允許的圖片副檔名</strong>：預設支援 .jpg/.png/.bmp/.webp/.tiff，可自行調整。</li>
</ul>
<p><strong>🗄️ 資料庫模式</strong></p>
<ul>
  <li><strong>SQLite 資料庫路徑（必填）</strong>：.sqlite 檔案的完整路徑。</li>
  <li><strong>SQL 查詢（必填）</strong>：查詢結果必須包含 <code>file_path</code> 欄位。</li>
</ul>
<p><strong>🌐 API 模式</strong></p>
<ul>
  <li><strong>API URL（必填）</strong>：返回圖片清單的 API 端點。</li>
  <li><strong>請求標頭</strong>：JSON 格式，例如 <code>{"Authorization": "Bearer token"}</code>。</li>
  <li><strong>回應資料路徑</strong>：用 dot-notation 指定 JSON 回應中圖片清單的位置，例如 <code>data.images</code>。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>若 Data Downloader 已完成下載，路徑會自動填入，直接按「▶ 執行」即可。</li>
  <li>每次執行都會建立一個新的 Manifest。舊的 Manifest 標注資料不會消失，可在歷史記錄中查看。</li>
  <li>同一個 Manifest 在整個工作流（標注、AI 預標注、匯出、同步）中共享使用。</li>
</ul>
""",

    "module_010_output": """
<h3>📦 Data Feeder — 結果說明</h3>
<p><strong>功能說明：</strong>顯示已建立 Manifest 的統計摘要，包括圖片總數、標注進度，並提供 CSV 匯出功能。</p>

<h4>📊 結果頁面說明</h4>
<ul>
  <li><strong>四個統計指標</strong>：
    <ul>
      <li>🔢 總圖片數：此 Manifest 包含的圖片總數。</li>
      <li>📦 已標注 BBox：已有框選標注（.json 檔案）的圖片數。</li>
      <li>🏷️ 已分類：已指定分類標籤的圖片數。</li>
      <li>⬜ 完全空白：尚未進行任何標注的圖片數。</li>
    </ul>
  </li>
  <li><strong>標注完成率</strong>：進度條顯示目前整體標注完成的百分比。</li>
  <li><strong>📤 Export CSV</strong>：下載包含所有圖片路徑的 CSV 檔案，可用 Excel 開啟查看。</li>
  <li><strong>歷史 Manifest 清單</strong>：展開可查看過去所有 Manifest 的建立記錄。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>統計數字在頁面重新整理時自動更新；若剛完成標注，稍等片刻再刷新即可看到最新數字。</li>
  <li>Manifest ID 是各模組識別目前工作資料集的唯一識別碼，不需手動操作。</li>
  <li>切換到其他模組（標注、AI 預標注等）時，系統會自動使用最新的 Manifest。</li>
</ul>
""",

    # ── module_012 ────────────────────────────────────────────────────────────
    "module_012_input": """
<h3>🏷️ Annotation — 使用說明</h3>
<p><strong>功能說明：</strong>設定標注工具（X-AnyLabeling 或 LabelMe）、標籤清單與分類選項，啟動後在外部視窗進行圖片標注。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>確認目前 Manifest（顯示於頁面頂部藍色框）是您要標注的資料集，若不對請回 Data Feeder 重新執行。</li>
  <li>選擇標注工具（預設 X-AnyLabeling）。</li>
  <li>在「標籤清單」文字框中輸入標籤名稱，每行一個，例如 <code>cat</code>、<code>dog</code>。</li>
  <li>若需要分類功能，在「分類選項」填入分類名稱（每行一個）。</li>
  <li>設定好後點擊「▶ 執行」，標注工具視窗會自動開啟並載入圖片。</li>
  <li>在 X-AnyLabeling 中完成標注後，回到此頁面的 Output 側查看進度。</li>
</ol>

<h4>📝 欄位說明</h4>
<ul>
  <li><strong>標注工具</strong>：X-AnyLabeling（推薦，支援 AI 輔助）或 LabelMe（傳統模式）。</li>
  <li><strong>標籤清單（建議填寫）</strong>：框選（BBox）標注時使用的標籤，每行一個，區分大小寫。</li>
  <li><strong>分類選項（選填）</strong>：整張圖片分類時使用，與 BBox 標籤互相獨立。</li>
  <li><strong>模型路徑（選填）</strong>：若要在 X-AnyLabeling 中使用 AI 輔助標注，指定 .pt 模型檔案路徑。</li>
  <li><strong>自動刷新間隔（選填）</strong>：Output 頁面自動偵測標注進度的刷新頻率（秒）。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>標籤清單若有重複（不分大小寫）會顯示警告，請移除重複項目。</li>
  <li>X-AnyLabeling 標注的結果會以 .json 格式存放在圖片同目錄。</li>
  <li>標注過程中不需關閉此頁面，Output 側會即時顯示進度。</li>
  <li>若 X-AnyLabeling 無法啟動，請確認程式已正確安裝，或聯絡管理員。</li>
</ul>
""",

    "module_012_output": """
<h3>🏷️ Annotation — 結果說明</h3>
<p><strong>功能說明：</strong>以主從式介面顯示標注進度，左側為圖片清單，右側為選取圖片的標注詳情。</p>

<h4>📊 頁面結構</h4>
<ul>
  <li><strong>左欄：圖片列表</strong>
    <ul>
      <li>🟢 已標注 / ⬜ 未標注 / 🏷️ 已分類 — 各圖片的標注狀態。</li>
      <li>使用頂部篩選按鈕（全部 / 已標注 / 未標注）過濾清單。</li>
      <li>點擊任一圖片，右欄會顯示該圖片的詳細資訊。</li>
      <li>超過 50 張自動分頁，可用「← 上一頁」「下一頁 →」翻頁。</li>
    </ul>
  </li>
  <li><strong>右欄：詳情面板</strong>
    <ul>
      <li>顯示原圖（或 BBox overlay 標注結果）。</li>
      <li>「標注明細」展開後顯示所有 BBox 的座標與標籤。</li>
      <li>「▲ 上一張」「▼ 下一張」按鈕切換圖片。</li>
      <li>「🏷️ 標注工具」按鈕可直接開啟 X-AnyLabeling 並跳至該圖片。</li>
    </ul>
  </li>
</ul>

<h4>⌨️ 鍵盤快捷鍵</h4>
<ul>
  <li><strong>↑ / K</strong>：選取上一張圖片</li>
  <li><strong>↓ / J</strong>：選取下一張圖片</li>
  <li><strong>A</strong>：開啟標注工具</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>標注結果由 X-AnyLabeling 直接寫到圖片同目錄的 .json 檔，頁面每次刷新時自動偵測最新狀態。</li>
  <li>若啟用了「自動刷新」，頁面會定期自動更新（可在 Input 頁調整間隔）。</li>
</ul>
""",

    # ── module_013 ────────────────────────────────────────────────────────────
    "module_013_input": """
<h3>🔄 Sync Back — 使用說明</h3>
<p><strong>功能說明：</strong>將目前 Manifest 的標注結果（BBox + 分類）批次 POST 至遠端 Service，同時附帶訓練格式壓縮檔。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>確認頁面頂部顯示的 Manifest 是您要同步的資料集。</li>
  <li>在「Service URL」填入後端服務網址。</li>
  <li>選擇「系統名稱」（iWISC / SMM）與「資料類型」（Simulation / Issue / Retrain）。</li>
  <li>在「Data Description」填寫說明文字，描述這批資料的來源或用途。</li>
  <li>選擇「送出範圍」：全部圖片或僅已標注的圖片。</li>
  <li>選擇要附帶的「訓練格式包」：COCO JSON、YOLO TXT，或不上傳格式包。</li>
  <li>確認「驗證摘要」無錯誤後，點擊「🚀 送出至 Service」。</li>
</ol>

<h4>📝 欄位說明</h4>
<ul>
  <li><strong>Service URL（必填）</strong>：後端服務的完整網址。</li>
  <li><strong>系統名稱（必填）</strong>：iWISC 或 SMM，決定 dataset_id 前綴。</li>
  <li><strong>資料類型（必填）</strong>：Simulation（模擬）/ Issue（問題件）/ Retrain（重訓）。</li>
  <li><strong>Data Description（建議填寫）</strong>：說明這批資料的用途，方便日後追溯。</li>
  <li><strong>送出範圍</strong>：「全部圖片」包含未標注的；「僅已標注」只送有 BBox 或分類的。</li>
  <li><strong>訓練格式包</strong>：COCO JSON（物件偵測）、YOLO TXT（YOLO 訓練），或不上傳。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>dataset_id 由系統自動產生（格式：系統_類型_YYYYMMDD），不需手動填寫。</li>
  <li>「驗證摘要」出現紅色錯誤時無法送出，請先修正標注問題。</li>
  <li>NT Account 與 Timestamp 由系統自動填入，不可修改。</li>
  <li>若選 partial 模式但無已標注項目，送出按鈕會停用。</li>
</ul>
""",

    "module_013_output": """
<h3>🔄 Sync Back — 結果說明</h3>
<p><strong>功能說明：</strong>顯示批次同步的結果，包括成功 / 失敗筆數、格式包上傳狀態，以及同步歷史記錄。</p>

<h4>📊 結果頁面說明</h4>
<ul>
  <li><strong>狀態標題</strong>：
    <ul>
      <li>✅ 同步完成 — 所有圖片資料成功送出。</li>
      <li>⚠️ 部分成功 — 部分圖片送出失敗（詳見 Chunk 詳情）。</li>
      <li>❌ 全部失敗 — 所有圖片均送出失敗，請檢查 Service URL 與網路連線。</li>
    </ul>
  </li>
  <li><strong>三個指標</strong>：成功送出筆數、失敗筆數、格式包上傳狀態。</li>
  <li><strong>Chunk 送出詳情</strong>：資料分批傳送，展開可查看各批次（Chunk）的成功與失敗情況。</li>
  <li><strong>同步歷史</strong>：展開可查看最近 10 筆同步記錄，包含時間、送出者、成功率。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>若格式包上傳失敗，原始 ZIP 檔案仍保留在本機，可手動重傳。</li>
  <li>同步成功後，可至「📥 Download」模組查詢並重新下載已同步的批次。</li>
</ul>
""",

    # ── module_020 ────────────────────────────────────────────────────────────
    "module_020_input": """
<h3>📥 Download — 使用說明</h3>
<p><strong>功能說明：</strong>查詢透過 Sync Back 上傳至 Service 的標注批次，選取後重新下載到本機。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>在「Service URL」欄位填入後端服務的網址（若 Sync Back 已設定，會自動帶入）。</li>
  <li>填寫查詢條件（NT Account、系統名稱、資料類型、日期範圍）。</li>
  <li>點擊「▶ 執行」查詢符合條件的批次。</li>
  <li>在右側 Output 頁面選取要下載的批次，按「⬇ Download」下載。</li>
</ol>

<h4>📝 欄位說明</h4>
<ul>
  <li><strong>Service URL（必填）</strong>：後端服務的完整網址。</li>
  <li><strong>NT Account（選填）</strong>：留空代表查詢所有人的記錄。</li>
  <li><strong>系統名稱（選填）</strong>：縮小查詢範圍，選「全部」不篩選。</li>
  <li><strong>資料類型（選填）</strong>：Simulation / Issue / Retrain，或「全部」。</li>
  <li><strong>日期區間（必填）</strong>：查詢的起始與結束日期，預設為最近 30 天。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>起始日期不可晚於結束日期，否則無法執行查詢。</li>
  <li>未填 NT Account 會查詢所有人的上傳記錄，通常只有管理員需要這樣使用。</li>
  <li>Service URL 若與 Sync Back 相同，系統會自動帶入，無需重複填寫。</li>
</ul>
""",

    "module_020_output": """
<h3>📥 Download — 結果說明</h3>
<p><strong>功能說明：</strong>顯示查詢到的上傳批次清單，選取後可下載並可選擇送至 Data Feeder 繼續作業。</p>

<h4>📊 頁面結構</h4>
<ul>
  <li><strong>下載結果通知</strong>：若剛完成下載，頁面頂部會顯示下載大小與解壓路徑。</li>
  <li><strong>查詢結果清單</strong>：以 Radio 按鈕列出符合條件的批次，每筆顯示：
    <ul>
      <li>上傳時間、系統名稱 / 資料類型、圖片張數、批次狀態（✅ 已接受 / ⏳ 處理中 / ❌ 失敗）。</li>
      <li>若有填寫 Description，也會顯示前 40 個字。</li>
    </ul>
  </li>
  <li><strong>⬇ Download 選取的批次</strong>：按此按鈕下載選取的 ZIP，完成後會顯示解壓路徑。</li>
  <li><strong>→ 送至 Data Feeder</strong>：下載完成後，點此自動將路徑填入 Data Feeder，方便繼續標注。</li>
  <li><strong>分頁控制</strong>：查詢結果超過一頁時，可用「◀ 上一頁」「下一頁 ▶」翻頁。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>狀態為「❌ 失敗」的批次無法下載，按鈕會自動停用。</li>
  <li>若查無記錄，請調整篩選條件（放寬日期範圍或移除系統名稱篩選）後重新查詢。</li>
</ul>
""",

    # ── module_014 ────────────────────────────────────────────────────────────
    "module_014_input": """
<h3>📤 Export — 使用說明</h3>
<p><strong>功能說明：</strong>將標注結果匯出為各種 ML 訓練框架所需格式，包括 COCO JSON、YOLO、Pascal VOC、ImageFolder 與 CSV。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>確認頁面頂部顯示的 Manifest 是您要匯出的資料集。</li>
  <li>在「匯出格式」中勾選一種或多種格式（可多選）。</li>
  <li>設定匯出目錄（點擊「📂 瀏覽」選擇，或直接貼上路徑）。</li>
  <li>視需要調整 Train / Val / Test 資料集比例（三者加總須等於 100%）。</li>
  <li>確認設定後，點擊「▶ 執行」開始匯出。</li>
</ol>

<h4>📝 欄位說明</h4>
<ul>
  <li><strong>匯出格式（必填，至少選一）</strong>：
    <ul>
      <li>COCO JSON：物件偵測訓練標準格式，兼容 Detectron2、MMDetection 等框架。</li>
      <li>YOLO txt：YOLO 系列模型訓練格式（v5 / v8 / v11 均支援）。</li>
      <li>Pascal VOC XML：VOC 格式，相容較舊的偵測框架。</li>
      <li>ImageFolder：圖片分類格式，依標籤建立子資料夾（需有分類標籤）。</li>
      <li>CSV：扁平格式，一行一個 BBox，可用 Excel 開啟。</li>
    </ul>
  </li>
  <li><strong>匯出目錄（必填）</strong>：匯出檔案存放的資料夾路徑。</li>
  <li><strong>Train / Val / Test 比例（選填）</strong>：三個數字加總須為 100，預設 70 / 15 / 15。</li>
  <li><strong>分層抽樣（Stratified）</strong>：勾選後依各標籤比例均衡分配至 Train/Val/Test。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>ImageFolder 格式需要有分類標籤，若已分類數為 0 請先在 Annotation 頁面完成分類。</li>
  <li>Train / Val / Test 三者比例加總必須等於 100，否則執行按鈕會停用。</li>
</ul>
""",

    "module_014_output": """
<h3>📤 Export — 結果說明</h3>
<p><strong>功能說明：</strong>顯示匯出任務的執行結果，包括各格式的輸出路徑與統計摘要。</p>

<h4>📊 結果頁面說明</h4>
<ul>
  <li><strong>匯出結果摘要</strong>：顯示每種格式的匯出狀態（✅ 成功 / ❌ 失敗）與輸出路徑。</li>
  <li><strong>統計資訊</strong>：已匯出的圖片數、BBox 數量、Train / Val / Test 分割結果。</li>
  <li><strong>各格式詳情</strong>：展開各格式的 Expander 可查看詳細檔案路徑與內容。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>匯出完成後，可直接將輸出資料夾拖入訓練框架使用。</li>
  <li>若某格式顯示失敗，請確認匯出目錄有寫入權限，並查看錯誤訊息。</li>
</ul>
""",

    # ── module_016 ────────────────────────────────────────────────────────────
    "module_016_input": """
<h3>🤖 AI Pre-labeling — 使用說明</h3>
<p><strong>功能說明：</strong>載入 YOLO 或分類模型，對當前 Manifest 的圖片批次自動推論，產生預標注結果供人工修正。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>確認頁面頂部顯示的 Manifest 是您要預標注的資料集。</li>
  <li>在「推論模式」選擇 YOLO（物件偵測）或 Image Classifier（圖片分類）。</li>
  <li>在「模型路徑」填入 .pt 模型檔案的路徑，或點擊「📂 瀏覽」選擇。</li>
  <li>調整「信心分數門檻」（建議從 0.25 開始，依結果調整）。</li>
  <li>視需要勾選「覆蓋已有標注」（預設跳過已有 .json 的圖片）。</li>
  <li>確認後點擊「▶ 執行」，右側 Output 頁面會顯示推論進度。</li>
</ol>

<h4>📝 欄位說明</h4>
<ul>
  <li><strong>推論模式（必填）</strong>：
    <ul>
      <li>YOLO：輸出 BBox + 標籤，寫成 X-AnyLabeling 格式，供標注工具修正。</li>
      <li>Image Classifier：輸出整張圖片的分類標籤，更新分類結果（ImageFolder 匯出可直接使用）。</li>
    </ul>
  </li>
  <li><strong>模型路徑（必填）</strong>：PyTorch .pt 權重檔，支援 YOLOv5 / v8 / v11。</li>
  <li><strong>信心分數門檻（必填）</strong>：介於 0.01 ~ 1.0，低於此值的預測結果會被丟棄。數字越大，輸出結果越精確但越少。</li>
  <li><strong>覆蓋已有標注（選填）</strong>：勾選後，已有 .json 的圖片也會重新推論並覆蓋。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>預標注只是輔助，結果需人工在 Annotation 工具中審查修正後再上傳。</li>
  <li>若找不到模型檔案，系統會顯示警告且無法執行。</li>
  <li>推論完成後，結果以 .json 格式存放在每張圖片的同目錄，可用 X-AnyLabeling 直接開啟修正。</li>
</ul>
""",

    "module_016_output": """
<h3>🤖 AI Pre-labeling — 結果說明</h3>
<p><strong>功能說明：</strong>顯示批次推論的執行進度與完成結果，包括各圖片的預標注狀態。</p>

<h4>📊 結果頁面說明</h4>
<ul>
  <li><strong>推論進度</strong>：執行中時顯示已處理圖片數 / 總張數，以及目前正在處理的圖片名稱。</li>
  <li><strong>完成摘要</strong>：
    <ul>
      <li>✅ 成功推論張數：已完成預標注的圖片數。</li>
      <li>⏭️ 跳過張數：因已有 .json 而被跳過的圖片（需勾選「覆蓋」才會重新推論）。</li>
      <li>❌ 失敗張數：推論出錯的圖片數（通常為圖片損毀或格式不支援）。</li>
    </ul>
  </li>
  <li><strong>圖片清單</strong>：顯示每張圖片的推論結果，可篩選查看成功 / 失敗 / 跳過的圖片。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>推論完成後，請前往 Annotation 模組用 X-AnyLabeling 開啟圖片，審查並修正預標注結果。</li>
  <li>若大量圖片推論失敗，請確認模型格式是否正確（需為 .pt，非 .onnx 或 .tflite）。</li>
</ul>
""",

    # ── module_017 ────────────────────────────────────────────────────────────
    "module_017_input": """
<h3>📊 管理中心 — 使用說明</h3>
<p><strong>功能說明：</strong>查看當前 Manifest 的標注統計儀表板，並管理標籤（改名 / 合併 / 刪除）。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>確認頁面頂部顯示的 Manifest 是您要查看的資料集。</li>
  <li>點擊「▶ 執行」（或等待頁面自動載入），右側 Output 頁面會顯示統計儀表板。</li>
  <li>在 Output 頁面的「標籤管理」區域可對標籤進行改名、合併或刪除操作。</li>
</ol>

<h4>📝 功能說明</h4>
<ul>
  <li><strong>此頁面僅顯示目前使用的 Manifest 資訊</strong>，若要切換請回 Data Feeder 重新執行。</li>
  <li>點擊「▶ 執行」後，右側會顯示完整的統計分析與標籤管理介面。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>標籤管理操作（改名、合併、刪除）會直接修改 .json 標注檔，建議操作前先備份資料。</li>
  <li>管理中心的標籤變更不會影響 X-AnyLabeling 的標籤設定，需手動同步。</li>
</ul>
""",

    "module_017_output": """
<h3>📊 管理中心 — 結果說明</h3>
<p><strong>功能說明：</strong>顯示標注進度統計儀表板，並提供標籤管理（改名 / 合併 / 刪除）操作介面。</p>

<h4>📊 統計儀表板</h4>
<ul>
  <li><strong>整體進度</strong>：圖片總數、已標注數、已分類數、完全空白數。</li>
  <li><strong>標籤分佈圖</strong>：各標籤的 BBox 數量長條圖，快速了解資料集的類別平衡。</li>
  <li><strong>標注狀態分佈</strong>：圓餅圖顯示已完成 / 未完成比例。</li>
</ul>

<h4>🏷️ 標籤管理操作</h4>
<ul>
  <li><strong>改名</strong>：將舊標籤名稱統一更換為新名稱，影響所有含該標籤的 .json 檔案。</li>
  <li><strong>合併</strong>：將多個標籤合併為一個，例如將「cat」和「Cat」合併為「cat」。</li>
  <li><strong>刪除</strong>：刪除指定標籤的所有 BBox 標注（操作不可逆，請謹慎）。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>所有標籤操作都會直接修改磁碟上的 .json 標注檔，<strong>操作前請務必備份</strong>。</li>
  <li>刪除標籤後，若重新執行「▶ 執行」可看到更新後的統計。</li>
</ul>
""",

    # ── module_018 ────────────────────────────────────────────────────────────
    "module_018_input": """
<h3>🖼️ Review Gallery — 使用說明</h3>
<p><strong>功能說明：</strong>以縮圖 Grid 方式快速瀏覽標注結果，可疊加 BBox overlay，並進行品質審查（Approve / Reject）。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>確認頁面頂部顯示的 Manifest 是您要審查的資料集。</li>
  <li>設定篩選條件：選擇要查看的圖片類型（全部 / 已標注 / 未標注 / 已分類 / 未分類）。</li>
  <li>調整「每行圖片數」（2 ~ 6 張），決定縮圖的大小。</li>
  <li>勾選「顯示 BBox overlay」後，縮圖上會疊加框選標注的方框。</li>
  <li>若只想查看特定標籤的圖片，在「標籤篩選」欄位輸入標籤名稱（例如 <code>cat</code>）。</li>
  <li>點擊「▶ 執行」載入 Gallery。</li>
</ol>

<h4>📝 欄位說明</h4>
<ul>
  <li><strong>篩選條件</strong>：快速過濾要查看的圖片類型。</li>
  <li><strong>每行圖片數</strong>：數字越大縮圖越小，建議 3 ~ 4 張（螢幕寬度 1080p 以上）。</li>
  <li><strong>顯示 BBox overlay</strong>：勾選後在縮圖上疊加標注框，方便快速視覺審查。</li>
  <li><strong>標籤篩選（選填）</strong>：只顯示含指定標籤的圖片，區分大小寫。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>若有大量圖片（數百張以上），建議先用篩選條件縮小範圍，避免頁面載入過慢。</li>
  <li>標籤篩選留空代表顯示全部，不會影響篩選條件的設定。</li>
</ul>
""",

    "module_018_output": """
<h3>🖼️ Review Gallery — 結果說明</h3>
<p><strong>功能說明：</strong>以 Grid 縮圖方式顯示圖片與標注 overlay，可逐張進行 Approve / Reject 品質審查。</p>

<h4>📊 頁面結構</h4>
<ul>
  <li><strong>縮圖 Grid</strong>：以每行 N 張（由 Input 設定）排列所有符合條件的圖片。
    <ul>
      <li>圖片上方顯示檔案名稱與標注狀態。</li>
      <li>若啟用 BBox overlay，標注框會疊加在縮圖上（顏色依標籤區分）。</li>
    </ul>
  </li>
  <li><strong>Approve / Reject 按鈕</strong>：每張圖片下方有兩個按鈕，用於品質審查。
    <ul>
      <li>✅ Approve：標記此圖標注品質合格。</li>
      <li>❌ Reject：標記此圖標注需要修正，會在清單中以特殊顏色顯示。</li>
    </ul>
  </li>
  <li><strong>分頁控制</strong>：超過一頁時使用「← 上一頁」「下一頁 →」翻頁，每頁顯示 50 張。</li>
</ul>

<h4>⚠️ 注意事項</h4>
<ul>
  <li>Approve / Reject 狀態會記錄在本機，重新載入 Gallery 後仍會保留。</li>
  <li>若縮圖顯示慢，可減少「每行圖片數」或先用篩選條件縮小範圍。</li>
  <li>Rejected 的圖片可回到 Annotation 模組重新標注，修正後可再次 Approve。</li>
</ul>
""",

    # ── module_021 ────────────────────────────────────────────────────────────
    "module_021_input": """
<h3>🔭 Vision DIY — 使用說明</h3>
<p><strong>功能說明：</strong>將部署在 k8s（或任何 HTTPS 位址）的 React Web App 嵌入平台，並讓它能直接觸發本地標注工具。</p>

<h4>📋 操作步驟</h4>
<ol>
  <li>在 <strong>Web App URL</strong> 欄位填入你的 HTTPS 網址，例如 <code>https://your-k8s-app.example.com</code>。</li>
  <li>按下「執行」按鈕，Output 頁面就會以 iframe 顯示該應用程式。</li>
  <li>之後只要切換到 Output 頁籤即可使用，不須每次重新執行（URL 已儲存在本機）。</li>
</ol>

<h4>⚠️ URL 規範</h4>
<ul>
  <li>必須以 <code>https://</code> 開頭，HTTP 不被支援。</li>
  <li>你的 k8s / nginx 服務需允許被 iframe 嵌入（見下方設定）。</li>
</ul>

<h4>🔧 k8s / nginx 必要設定</h4>
<p>若 iframe 顯示空白，代表伺服器阻擋了嵌入。請在 nginx server block 或 ingress 加入：</p>
<pre style="background:#1e293b;color:#e2e8f0;padding:12px 16px;border-radius:8px;font-size:12px;line-height:1.6;">
add_header X-Frame-Options "ALLOWALL" always;
add_header Content-Security-Policy "frame-ancestors *" always;
</pre>
<p>若使用 <strong>k8s ingress-nginx</strong>，在 Ingress manifest 的 annotation 加入：</p>
<pre style="background:#1e293b;color:#e2e8f0;padding:12px 16px;border-radius:8px;font-size:12px;line-height:1.6;">
nginx.ingress.kubernetes.io/configuration-snippet: |
  add_header X-Frame-Options "ALLOWALL" always;
  add_header Content-Security-Policy "frame-ancestors *" always;
</pre>
<p><code>always</code> 確保錯誤頁面也套用，避免 Chromium 在某些狀況仍然拒絕渲染。</p>
""",

    "module_021_output": """
<h3>🔭 Vision DIY — 輸出說明</h3>
<p><strong>功能說明：</strong>全版顯示外部 Web App，並橋接 postMessage 讓它能呼叫本地標注工具。</p>

<h4>📡 postMessage 橋接協定</h4>
<p>在你的 React App 裡，用以下程式碼觸發本地動作：</p>
<pre style="background:#1e293b;color:#e2e8f0;padding:12px 16px;border-radius:8px;font-size:12px;line-height:1.6;">
// ① 直接開啟 X-AnyLabeling 標記指定圖片（圖片會從 URL 下載到本機）
window.parent.postMessage({
  cim: "v1",
  action: "open_xanylabeling",
  imageUrl: "https://your-server.com/image.jpg"
}, "*");

// ② 將圖片加入標注佇列（TopBar 顯示計數）
window.parent.postMessage({
  cim: "v1",
  action: "queue_image",
  imageUrl: "https://your-server.com/image.jpg",
  metadata: { label: "defect" }  // 選填
}, "*");
</pre>

<h4>🔧 k8s / nginx 必要設定</h4>
<p>若 iframe 顯示空白，請在 nginx 加入以下 header（<code>always</code> 確保錯誤頁也套用）：</p>
<pre style="background:#1e293b;color:#e2e8f0;padding:12px 16px;border-radius:8px;font-size:12px;line-height:1.6;">
add_header X-Frame-Options "ALLOWALL" always;
add_header Content-Security-Policy "frame-ancestors *" always;
</pre>
<p>k8s ingress-nginx 的 Ingress manifest annotation：</p>
<pre style="background:#1e293b;color:#e2e8f0;padding:12px 16px;border-radius:8px;font-size:12px;line-height:1.6;">
nginx.ingress.kubernetes.io/configuration-snippet: |
  add_header X-Frame-Options "ALLOWALL" always;
  add_header Content-Security-Policy "frame-ancestors *" always;
</pre>

<h4>📂 本機存放路徑</h4>
<ul>
  <li>下載的圖片：<code>{CIM_LOG_DIR}/external-queue/</code></li>
  <li>xanylabeling GUI 狀態：<code>{CIM_LOG_DIR}/xanylabeling_state/external/</code></li>
</ul>
""",
}


# ─────────────────────────────────────────────────────────────────────────────
# 主函式
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """<style>
.cim-help-toggle { display: none; }
.cim-help-badge {
    display: inline-flex; align-items: center; justify-content: center;
    width: 16px; height: 16px; border-radius: 50%;
    background: #1a73e8; color: #fff; font-size: 11px; font-weight: bold;
    cursor: pointer; user-select: none; opacity: 0.7; transition: opacity .15s;
    vertical-align: middle; line-height: 1; margin-left: 4px;
}
.cim-help-badge:hover { opacity: 1; }
.cim-help-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,.45); z-index: 99999;
    align-items: center; justify-content: center;
}
.cim-help-toggle:checked ~ .cim-help-overlay { display: flex; }
.cim-help-backdrop { position: absolute; inset: 0; cursor: pointer; z-index: 0; }
.cim-help-card {
    position: relative; z-index: 1; background: #fff;
    border-radius: 12px; padding: 32px 36px;
    max-width: 720px; width: 92vw; max-height: 80vh;
    overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,.22);
}
.cim-help-card h3 { margin-top: 0; color: #1a73e8; }
.cim-help-card h4 { color: #333; margin-top: 20px; }
.cim-help-card ol, .cim-help-card ul { padding-left: 20px; line-height: 1.8; }
.cim-help-card code { background: #f0f4ff; padding: 1px 5px; border-radius: 4px; }
.cim-help-close {
    position: absolute; top: 14px; right: 18px;
    font-size: 22px; cursor: pointer; color: #666; line-height: 1; display: block;
}
.cim-help-close:hover { color: #111; }
.cim-help-heading {
    font-size: 1.25rem; font-weight: 600; color: rgb(49, 51, 63);
    margin: 0.25rem 0 0.15rem 0; padding: 0; line-height: 1.4; display: block;
}
</style>"""


def render_help_button(module_id: str, side: str = "input", title: str = "") -> None:
    """Inline ? badge; click opens user manual modal.

    Args:
        title: When provided, renders an <h3> heading with the badge inline —
               replaces the caller's st.subheader() call.  When empty, renders
               only a compact 22-px badge row (backward-compat).

    Uses a pure-CSS checkbox trick — no JavaScript needed, works inside Streamlit's
    React renderer which strips onclick and <script> tags from st.markdown HTML.

    CSS is inlined into every call (not session_state-guarded) so the render tree
    always has exactly one st.markdown element. A guard would cause the tree to
    shrink on reruns ([CSS, badge] → [badge]), making React move elements and
    produce a visible layout shift.
    """

    uid = f"cim-help-{module_id}-{side}"
    content_key = f"{module_id}_{side}"
    html_content = _HELP_CONTENT.get(content_key, "<p>（尚無使用說明）</p>")

    # ── Badge + Modal — always one st.markdown call, structure never changes ──
    # DOM order: input(toggle) → content → div(overlay)
    # CSS rule ".cim-help-toggle:checked ~ .cim-help-overlay { display:flex }"
    # makes the overlay visible when the checkbox is checked. Labels toggle it.
    _toggle = f'<input type="checkbox" class="cim-help-toggle" id="{uid}-toggle">'
    _badge  = f'<label for="{uid}-toggle" class="cim-help-badge" title="查看使用說明">?</label>'
    _overlay = (
        f'<div class="cim-help-overlay">'
        f'<label for="{uid}-toggle" class="cim-help-backdrop"></label>'
        f'<div class="cim-help-card">'
        f'<label for="{uid}-toggle" class="cim-help-close" title="關閉">✕</label>'
        f'{html_content}'
        f'</div></div>'
    )

    if title:
        _markdown_html(
            f'{_CSS}'
            f'<div style="overflow:visible;margin:0 0 4px 0;">'
            f'{_toggle}'
            f'<span class="cim-help-heading">{title} {_badge}</span>'
            f'{_overlay}'
            f'</div>',
        )
    else:
        _markdown_html(
            f'{_CSS}'
            f'<div style="height:22px;margin:0 0 2px 0;overflow:visible;">'
            f'{_toggle}{_badge}{_overlay}'
            f'</div>',
        )


def _markdown_html(markup: str) -> None:
    try:
        st.markdown(markup, unsafe_allow_html=True)
    except TypeError:
        st.markdown(markup)
