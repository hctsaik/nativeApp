# Streamlit Output 頁效能模式

> 這份文件記錄 module_012 優化（2026-05）所產生的三個可重用模式。
> 規則摘要已寫入 `CLAUDE.md`；此文件提供背景與完整範例。

## 問題根源

Streamlit 每次使用者互動（按按鈕、切 selectbox、鍵盤快捷鍵）都會完整重執行整個
render 函式。Output 頁若在 render 函式內直接對 N 張圖片做檔案掃描，
等效於把 O(N) 的 I/O 乘上互動次數。

`st_autorefresh` 每 30 秒再觸發一次，問題會持續惡化。

---

## 模式 1：session_state 快取 + mtime 增量更新

### 為什麼 mtime，不是 hash？

| 方案 | 成本 | 備注 |
|------|------|------|
| 每次重新讀 JSON | O(N) 讀檔 + 解析 | 原始問題 |
| stat().st_mtime 比對 | O(N) syscall（只讀 inode，不讀內容） | **選用** |
| 檔案 hash | O(N) 讀全檔 | 比 mtime 貴，無必要 |

`st_mtime` 在 X-AnyLabeling 存檔時必定更新，精度足夠（秒級），且不需讀檔案內容。

### 實作骨架

```python
def _scan_items(db_items):
    """Full scan，記錄每個 ann_path 的 mtime。"""
    items, mtimes = [], {}
    for it in db_items:
        fp = it["file_path"]
        has_ann, ann_path, shape_count = _find_annotation(fp)
        items.append({**it, "has_ann": has_ann, "ann_path": ann_path, "shape_count": shape_count})
        if ann_path:
            try:    mtimes[ann_path] = Path(ann_path).stat().st_mtime
            except: mtimes[ann_path] = 0.0
    return items, mtimes


def _incremental_refresh(cached, mtimes):
    """只對 mtime 改變的項目重讀 JSON。"""
    new_mtimes = dict(mtimes)
    for item in cached:
        fp, ann_path = item["file_path"], item["ann_path"]
        if ann_path:
            try:    mtime = Path(ann_path).stat().st_mtime
            except FileNotFoundError: mtime = -1.0
            if mtime != new_mtimes.get(ann_path, -999.0):
                has_ann, new_ap, sc = _find_annotation(fp)
                item.update(has_ann=has_ann, ann_path=new_ap, shape_count=sc)
                new_mtimes.pop(ann_path, None)
                if new_ap:
                    try: new_mtimes[new_ap] = Path(new_ap).stat().st_mtime
                    except: pass
        else:
            # 尚無標注：只做 exists()，不讀內容
            if Path(fp).with_suffix(".json").exists():
                has_ann, new_ap, sc = _find_annotation(fp)
                item.update(has_ann=has_ann, ann_path=new_ap, shape_count=sc)
                if new_ap:
                    try: new_mtimes[new_ap] = Path(new_ap).stat().st_mtime
                    except: pass
    return cached, new_mtimes


def _get_items(manifest_id, db_items):
    """session_state 快取入口。"""
    cached = st.session_state.get("items")
    if (
        st.session_state.get("cache_mid") != manifest_id
        or cached is None
        or len(cached) != len(db_items)   # manifest 有新增項目時重掃
    ):
        items, mtimes = _scan_items(db_items)
    else:
        items, mtimes = _incremental_refresh(cached, st.session_state["mtimes"])

    st.session_state["items"]     = items
    st.session_state["mtimes"]    = mtimes
    st.session_state["cache_mid"] = manifest_id
    return items
```

### 複用時注意事項

- cache key 名稱（`"items"`, `"mtimes"`, `"cache_mid"`）加上模組前綴，避免不同頁面衝突
  （module_012 用 `"m012_items"` 等）
- `len(cached) != len(db_items)` 這個檢查確保 manifest 新增圖片後 cache 不會過舊
- annotation 被刪除時 `stat()` 拋 `FileNotFoundError`，mtime 設為 -1.0 觸發重掃

---

## 模式 2：分頁（Virtual Scroll）

### 頁面大小選擇

| PAGE_SIZE | 每次 rerun widget 數 | 體感 |
|-----------|---------------------|------|
| 全部（N=500） | 500×(3欄+2按鈕+1caption) | 明顯卡頓 |
| 100 | 600 widgets | 邊界 |
| **50** | **300 widgets** | 流暢 |
| 20 | 120 widgets | 翻頁頻繁 |

### 實作骨架

```python
PAGE_SIZE = 50

# ── 分頁計算（在 with left_col: 內，filter 之後）────────────────────
# 篩選切換時重設頁碼
if st.session_state.get("prev_filter") != filter_opt:
    st.session_state["page"] = 0
    st.session_state["prev_filter"] = filter_opt

n_visible = len(visible)
n_pages   = max(1, (n_visible + PAGE_SIZE - 1) // PAGE_SIZE)
page      = max(0, min(st.session_state.get("page", 0), n_pages - 1))
sel_idx   = st.session_state.get("selected_idx", 0)

# 鍵盤導覽：選取項目不在當頁時自動跳頁
for _vi, _it in enumerate(visible):
    if item_id_to_global.get(_it["item_id"]) == sel_idx:
        desired = _vi // PAGE_SIZE
        if desired != page:
            page = desired
            st.session_state["page"] = page
        break

page_items = visible[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

# ── 只 render 當頁 ────────────────────────────────────────────────────
for vis_i, item in enumerate(page_items):
    ...

# ── 分頁按鈕（else 區塊底部）─────────────────────────────────────────
if n_pages > 1:
    col_prev, col_info, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀", disabled=(page == 0), use_container_width=True):
            st.session_state["page"] = page - 1
            st.rerun()
    with col_info:
        st.caption(f"第 {page + 1} / {n_pages} 頁（共 {n_visible} 張）")
    with col_next:
        if st.button("▶", disabled=(page == n_pages - 1), use_container_width=True):
            st.session_state["page"] = page + 1
            st.rerun()
```

---

## 模式 3：O(1) 全域索引查表

### 問題

```python
# ❌ visible loop 內的 items.index(item)
# visible 有 M 項、items 有 N 項 → O(M×N) 總成本
for item in visible:
    global_idx = items.index(item)   # 每次線性搜尋
```

N=1000 全部顯示時：1000×1000 = 100 萬次 dict 比對。

### 修法

```python
# ✅ loop 前建一次 dict，loop 內 O(1)
item_id_to_global = {it["item_id"]: i for i, it in enumerate(items)}

for vis_i, item in enumerate(page_items):
    global_idx = item_id_to_global.get(item["item_id"], page_start + vis_i)
```

fallback `page_start + vis_i` 在 item_id 為空字串時使用，不影響正常流程。

---

## 性能對照（估算，N=1000 張）

| 操作 | 改前（每次 rerun） | 改後（每次 rerun） |
|------|-------------------|-------------------|
| 標注狀態掃描 | 1000×json.loads ≈ 300–1000ms | 1000×stat() ≈ 1–5ms |
| 左欄 widget 建立 | 1000×(3欄+2鈕) | 50×(3欄+2鈕) |
| 全域索引查找 | O(N²) = 100萬次 | O(N) = 1000次 hash |

---

## 現有實作位置

- 完整範例：`sidecar/python-engine/scripts/module_012/012_output.py`
  - `_scan_items()` — line ~109
  - `_incremental_refresh()` — line ~125
  - `_get_items()` — line ~170
  - Pagination 計算 — `render_output()` 內的左欄區塊
