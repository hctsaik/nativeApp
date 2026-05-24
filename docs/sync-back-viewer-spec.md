# Sync Back Viewer — 開發規格文件

> 本文件供另一個 AI / 開發團隊快速理解 **CIM Sync Back 服務的 API 合約**，
> 以及如何開發一個獨立的 **React Viewer 專案**來讀取標註資料，
> 並選擇性整合進 CIM 平台的 Vision DIY iframe。

---

## 1. 背景

CIM Hybrid Edge Platform 的標註工具（module_013 Sync Back）會將使用者的影像標註結果
以 JSON chunks 方式打到後端服務（稱為 **Service**）。

Viewer 專案的目標：
- **讀取** Service 上的批次提交記錄（清單、詳情）
- **顯示** 每張影像及其疊加的標註框（BBox / Polygon）
- **選擇性** 整合進 CIM platform 作為 Vision DIY 的前端（透過 iframe + postMessage）

---

## 2. Service API Contract

所有端點的 base URL 從環境變數 `VITE_SERVICE_URL` 取得（例如 `https://your-service.k8s`）。

### 2.1 列出批次提交記錄

```
GET /api/v1/submissions
```

**Query Parameters：**

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `page` | int | 否 | 頁碼（1-based，預設 1）|
| `page_size` | int | 否 | 每頁筆數（預設 20）|
| `nt_account` | string | 否 | 過濾提交者帳號（例如 `HCTSAIK`）|
| `system_name` | string | 否 | `iWISC` \| `SMM` |
| `data_type` | string | 否 | `Simulation` \| `Issue` \| `Retrain` |
| `date_from` | string | 否 | `YYYY-MM-DD` |
| `date_to` | string | 否 | `YYYY-MM-DD` |

**Response：**

```json
{
  "total": 150,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "submit_id": "550e8400-e29b-41d4-a716-446655440000",
      "dataset_id": "iWISC_Simulation_20260524",
      "nt_account": "HCTSAIK",
      "system_name": "iWISC",
      "data_type": "Simulation",
      "description": "第一批瑕疵標注",
      "timestamp": "2026-05-24 10:30:00",
      "item_count": 200,
      "scope": "full"
    }
  ]
}
```

> `dataset_id` 格式：`{system_name}_{data_type}_{YYYYMMDD}`

---

### 2.2 提交標註資料（由 CIM 平台呼叫，Viewer 不需實作）

```
POST /api/v1/datasets/{dataset_id}/submissions
Content-Type: application/json
```

每次 POST 為一個 chunk（最多 100 筆），整批共用同一個 `submit_id`。

**Request Body：**

```json
{
  "submit_id": "uuid-v4",
  "scope": "full",
  "chunk_index": 0,
  "total_chunks": 3,
  "metadata": {
    "system_name": "iWISC",
    "data_type": "Simulation",
    "nt_account": "HCTSAIK",
    "timestamp": "2026-05-24 10:30:00",
    "description": "批次說明文字"
  },
  "items": [
    {
      "item_id": "uuid",
      "file_name": "image_001.jpg",
      "classification": "",
      "shapes": [
        {
          "label": "defect",
          "shape_type": "rectangle",
          "x1": 10,
          "y1": 20,
          "x2": 100,
          "y2": 200,
          "polygon_pts": []
        },
        {
          "label": "scratch",
          "shape_type": "polygon",
          "x1": 30,
          "y1": 40,
          "x2": 80,
          "y2": 90,
          "polygon_pts": [[30, 40], [80, 40], [80, 90], [30, 90]]
        }
      ]
    }
  ]
}
```

**Shape 欄位說明：**

| 欄位 | 說明 |
|------|------|
| `shape_type` | `rectangle` 或 `polygon` |
| `x1, y1, x2, y2` | BBox 的左上角與右下角（像素座標）|
| `polygon_pts` | `[[x, y], ...]`，shape_type=polygon 時有值 |
| `classification` | item 層級的分類標籤（字串，可為空）|

**Response：**

```json
{ "ok": true }
```

---

### 2.3 上傳格式 ZIP（由 CIM 平台呼叫，Viewer 不需實作）

```
POST /api/v1/datasets/{dataset_id}/submissions/{submit_id}/exports
Content-Type: multipart/form-data
```

Form fields：
- `format`：`coco_json` 或 `yolo_txt`
- `file`：ZIP 檔案（`application/zip`）

ZIP 內容（`coco_json`）：
```
annotations.json   ← COCO 標準格式
```

ZIP 內容（`yolo_txt`）：
```
classes.txt
data.yaml
labels/
  image_001.txt
  image_002.txt
  ...
```

**Response：**

```json
{ "ok": true }
```

---

### 2.4 下載批次 ZIP（Viewer 可選用）

```
GET /api/v1/submissions/{submit_id}/download?nt_account=HCTSAIK
```

**Response：** `Content-Type: application/zip`（串流下載）

ZIP 中包含該批次的格式資料（COCO JSON 或 YOLO TXT）。

---

### 2.5 取得批次詳細項目（建議 Service 新增）

```
GET /api/v1/submissions/{submit_id}/items?page=1&page_size=50
```

> **此端點目前不確定 Service 是否實作**，建議由 Service 端補充。
> Viewer 若無此端點則需透過 ZIP 解壓取得資料。

**建議 Response：**

```json
{
  "total": 200,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "item_id": "uuid",
      "file_name": "image_001.jpg",
      "image_url": "https://your-service.k8s/images/uuid.jpg",
      "classification": "",
      "shapes": [...]
    }
  ]
}
```

> `image_url` 需可直接 `<img src>` 存取（無需額外 auth，或使用短期 token）。

---

## 3. 驗證規則（了解 CIM 端的資料品質標準）

CIM 在送出前會做以下檢查，Service 端可選擇性重做驗證：

| 驗證碼 | 嚴重度 | 條件 |
|--------|--------|------|
| `invalid_bbox` | error | `x2 <= x1` 或 `y2 <= y1` |
| `empty_label` | error | shape 的 `label` 為空字串 |
| `high_empty_ratio` | warning | 超過 30% 的 item 既無 shapes 也無 classification |

Error 級別會阻止提交；Warning 僅提示，不阻止。

---

## 4. Viewer 專案建議架構（Vite + React）

### 4.1 專案初始化

```bash
npm create vite@latest sync-back-viewer -- --template react
cd sync-back-viewer
npm install
```

**`.env.local`（本地開發）：**
```
VITE_SERVICE_URL=https://your-service.k8s
VITE_DEFAULT_NT_ACCOUNT=HCTSAIK
```

### 4.2 目錄結構

```
sync-back-viewer/
├── index.html
├── vite.config.js
├── .env.local
├── package.json
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── api/
    │   └── service.js          ← 所有 HTTP 呼叫集中在這
    ├── components/
    │   ├── FilterBar.jsx        ← system/data_type/日期過濾 + 搜尋
    │   ├── SubmissionList.jsx   ← 左欄：批次清單（分頁）
    │   ├── SubmissionDetail.jsx ← 右欄：選中批次的圖片列表
    │   ├── ImageCanvas.jsx      ← Canvas 疊加 shapes
    │   └── ShapeOverlay.jsx     ← 單一 shape 繪製邏輯
    ├── hooks/
    │   ├── useSubmissions.js    ← 分頁查詢 + 狀態管理
    │   └── useCimBridge.js      ← CIM postMessage 橋接
    └── styles/
        └── App.css
```

### 4.3 `src/api/service.js`

```js
const BASE = import.meta.env.VITE_SERVICE_URL;

export async function listSubmissions({
  page = 1,
  pageSize = 20,
  ntAccount = '',
  systemName = '',
  dataType = '',
  dateFrom = '',
  dateTo = '',
} = {}) {
  const qs = new URLSearchParams({ page, page_size: pageSize });
  if (ntAccount) qs.set('nt_account', ntAccount);
  if (systemName) qs.set('system_name', systemName);
  if (dataType)   qs.set('data_type', dataType);
  if (dateFrom)   qs.set('date_from', dateFrom);
  if (dateTo)     qs.set('date_to', dateTo);

  const res = await fetch(`${BASE}/api/v1/submissions?${qs}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
  // → { total, page, page_size, items: [...] }
}

export async function getSubmissionItems(submitId, { page = 1, pageSize = 50 } = {}) {
  const qs = new URLSearchParams({ page, page_size: pageSize });
  const res = await fetch(`${BASE}/api/v1/submissions/${submitId}/items?${qs}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
  // → { total, page, page_size, items: [{ item_id, file_name, image_url, shapes }] }
}

export function getDownloadUrl(submitId, ntAccount) {
  return `${BASE}/api/v1/submissions/${submitId}/download?nt_account=${ntAccount}`;
}
```

### 4.4 `src/hooks/useSubmissions.js`

```js
import { useState, useCallback } from 'react';
import { listSubmissions } from '../api/service';

export function useSubmissions() {
  const [submissions, setSubmissions] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetch = useCallback(async (filters = {}, p = 1) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSubmissions({ ...filters, page: p });
      setSubmissions(data.items);
      setTotal(data.total);
      setPage(p);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  return { submissions, total, page, loading, error, fetch, setPage };
}
```

### 4.5 `src/components/ImageCanvas.jsx`

```jsx
import { useEffect, useRef } from 'react';

const COLORS = ['#00ff88', '#ff4466', '#44aaff', '#ffcc00'];

export function ImageCanvas({ imageSrc, shapes = [], width = 640, height = 480 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!imageSrc) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = imageSrc;
    img.onload = () => {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      ctx.drawImage(img, 0, 0);

      const labelSet = [...new Set(shapes.map(s => s.label))];
      const colorMap = Object.fromEntries(
        labelSet.map((l, i) => [l, COLORS[i % COLORS.length]])
      );

      for (const s of shapes) {
        const color = colorMap[s.label] || '#ffffff';
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.fillStyle = color + '26'; // 15% opacity

        if (s.shape_type === 'rectangle') {
          const w = s.x2 - s.x1;
          const h = s.y2 - s.y1;
          ctx.fillRect(s.x1, s.y1, w, h);
          ctx.strokeRect(s.x1, s.y1, w, h);
        } else if (s.shape_type === 'polygon' && s.polygon_pts?.length) {
          ctx.beginPath();
          s.polygon_pts.forEach(([x, y], i) =>
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
          );
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
        }

        // Label text
        ctx.fillStyle = color;
        ctx.font = '13px sans-serif';
        ctx.fillText(s.label, s.x1 + 2, s.y1 - 4);
      }
    };
  }, [imageSrc, shapes]);

  return (
    <canvas
      ref={canvasRef}
      style={{ maxWidth: '100%', border: '1px solid #333' }}
    />
  );
}
```

### 4.6 `src/hooks/useCimBridge.js`（CIM Vision DIY 整合）

```js
import { useEffect, useCallback } from 'react';

/**
 * 若此 Viewer 嵌入在 CIM platform 的 Vision DIY iframe 中，
 * 可透過 postMessage 觸發 CIM 的標註工具。
 * 
 * 獨立執行（非 iframe）時，這些函式為 no-op。
 */
export function useCimBridge() {
  const isEmbedded = window.self !== window.top;

  // 接收來自 CIM 的指令（選填）
  useEffect(() => {
    if (!isEmbedded) return;
    const handler = (e) => {
      if (e.data?.cim === 'v1') {
        console.log('[CIM Bridge] received:', e.data);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [isEmbedded]);

  /** 開啟 xanylabeling 標記指定影像 */
  const openXanylabeling = useCallback((imageUrl, metadata = {}) => {
    window.parent.postMessage(
      { cim: 'v1', type: 'open-xanylabeling', payload: { image_url: imageUrl, metadata } },
      '*'
    );
  }, []);

  /** 把影像加入 CIM Annotation 頁面的佇列 */
  const queueImage = useCallback((imageUrl, metadata = {}) => {
    window.parent.postMessage(
      { cim: 'v1', type: 'queue-image', payload: { image_url: imageUrl, metadata } },
      '*'
    );
  }, []);

  return { isEmbedded, openXanylabeling, queueImage };
}
```

### 4.7 `src/App.jsx`（骨架）

```jsx
import { useState } from 'react';
import { FilterBar } from './components/FilterBar';
import { SubmissionList } from './components/SubmissionList';
import { SubmissionDetail } from './components/SubmissionDetail';
import { useSubmissions } from './hooks/useSubmissions';

export default function App() {
  const { submissions, total, page, loading, error, fetch, setPage } = useSubmissions();
  const [filters, setFilters] = useState({});
  const [selected, setSelected] = useState(null);

  function handleFilter(newFilters) {
    setFilters(newFilters);
    fetch(newFilters, 1);
  }

  function handleSelect(submission) {
    setSelected(submission);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <FilterBar onFilter={handleFilter} />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <SubmissionList
          items={submissions}
          total={total}
          page={page}
          loading={loading}
          error={error}
          selected={selected}
          onSelect={handleSelect}
          onPageChange={(p) => { setPage(p); fetch(filters, p); }}
        />
        <SubmissionDetail submission={selected} />
      </div>
    </div>
  );
}
```

---

## 5. CIM Vision DIY 整合說明

若 Viewer 要嵌入 CIM platform（Vision DIY iframe），需滿足以下條件：

### 5.1 Server 端（k8s nginx/ingress）必須設定

```nginx
# 獨立 nginx 設定
add_header X-Frame-Options "ALLOWALL" always;
add_header Content-Security-Policy "frame-ancestors *" always;
```

```yaml
# k8s ingress-nginx annotation
nginx.ingress.kubernetes.io/configuration-snippet: |
  add_header X-Frame-Options "ALLOWALL" always;
  add_header Content-Security-Policy "frame-ancestors *" always;
```

> 未設定此項，Chromium 會拒絕渲染 iframe（顯示空白）。

### 5.2 postMessage 協議

Viewer 透過 `window.parent.postMessage` 呼叫 CIM 功能：

```js
// 開啟 xanylabeling 標記影像
window.parent.postMessage({
  cim: 'v1',
  type: 'open-xanylabeling',
  payload: {
    image_url: 'https://your-service.k8s/images/xxx.jpg',
    metadata: { source: 'sync-back-viewer', item_id: 'uuid' }
  }
}, '*');

// 把影像加入 Annotation 佇列
window.parent.postMessage({
  cim: 'v1',
  type: 'queue-image',
  payload: {
    image_url: 'https://your-service.k8s/images/xxx.jpg'
  }
}, '*');
```

CIM 平台收到訊息後會轉呼叫：
- `open-xanylabeling` → 下載影像並開啟 xanylabeling 標記工具
- `queue-image` → 下載影像並加入 Annotation 頁面的佇列

### 5.3 在 CIM 中設定 Vision DIY URL

在 CIM annotation_workflow sheet → Vision DIY tab → Input 頁面：
1. 填入 Viewer 的 HTTPS URL（例如 `https://viewer.k8s`）
2. 按「執行」
3. Output 頁面會以 iframe 載入 Viewer

---

## 6. 給 Service 端開發團隊的需求清單

```
# Service API 補充需求

## 必要端點（目前已知 CIM 使用）
1. POST /api/v1/datasets/{dataset_id}/submissions
2. POST /api/v1/datasets/{dataset_id}/submissions/{submit_id}/exports
3. GET  /api/v1/submissions（清單 + 分頁過濾）
4. GET  /api/v1/submissions/{submit_id}/download

## 建議新增（Viewer 需要）
5. GET /api/v1/submissions/{submit_id}/items?page=1&page_size=50
   → 回傳每筆 item 的 image_url（可直接 <img src> 存取）+ shapes

## CORS 設定
- 開發：允許 http://localhost:5173
- 正式：允許 Viewer 的 origin

## 影像存取
- 每筆 item 需提供可直接 GET 的 image_url
- 若需 auth，建議使用短期 signed URL（15~60 分鐘有效）

## iframe 允許（嵌入 CIM 用）
- nginx 設定 X-Frame-Options: ALLOWALL
- nginx 設定 Content-Security-Policy: frame-ancestors *

## 測試資料
- 提供至少一個 dataset_id 和對應 submit_id，含影像 URL，供 Viewer 開發驗測用
```

---

## 7. 建議開發順序

| 階段 | 工作 | 預計時間 |
|------|------|----------|
| Day 1 | 用靜態 mock JSON 渲染批次清單（FilterBar + SubmissionList）| 半天 |
| Day 1 | 接通 `GET /api/v1/submissions`，替換 mock | 半天 |
| Day 2 | 取得 items 資料（優先接 API；無 API 則解壓 ZIP）| 1 天 |
| Day 3 | ImageCanvas 疊加 shapes（rectangle 先，polygon 後）| 1 天 |
| Day 4 | postMessage bridge 測試（填 Vision DIY URL，驗證 open-xanylabeling）| 半天 |
| Day 4 | nginx iframe 設定驗證 | 半天 |

---

## 8. 資料模型速查

### dataset_id 組成規則
```
{system_name}_{data_type}_{YYYYMMDD}
例：iWISC_Simulation_20260524
    SMM_Issue_20260601
```

### system_name 選項
- `iWISC`
- `SMM`

### data_type 選項
- `Simulation`
- `Issue`
- `Retrain`

### shape_type
- `rectangle`：用 `x1, y1, x2, y2`（左上、右下像素座標）
- `polygon`：用 `polygon_pts: [[x, y], ...]`（同時有 `x1,y1,x2,y2` 作為 bounding box）

---

*文件產生時間：2026-05-24*
*對應 CIM 版本：module_013 Sync Back v1*
