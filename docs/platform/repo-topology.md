# Repo 拓樸：平台 + 外掛（submodule / 外部 junction）

> nativeApp 是**平台**；各功能外掛活在自己的 repo，以不同方式掛回平台。
> 本文記錄三個 repo 的關係、labeling 的「外部 junction」掛法，以及它帶來的關鍵約束。
> 相關藍圖見 [`labeling-independence-plan.md`](labeling-independence-plan.md)（§3 P4 為本決策）。

## 1. 全貌

```
nativeApp/                                    平台（本 repo，github.com/hctsaik/nativeApp）
└─ sidecar/python-engine/
   ├─ core/  scripts/  ...                    平台共用層（host 提供給外掛）
   └─ plugins/
      ├─ bi/                                  （in-tree plugin）
      └─ labeling/  ──junction──►  ../../../../../ANnoTation
   └─ vendor/
      ├─ AI4BI/     ── git submodule ──►  github.com/hctsaik/AI4BI
      └─ LV/        ── git submodule ──►  github.com/hctsaik/LV  (branch: uihuang_dev)

c:\code\claude\ANnoTation                     labeling 外掛原始碼（獨立 repo，github.com/hctsaik/ANnoTation）
```

## 2. 各外掛的掛載方式

| 外掛 | repo | 掛載點 | 掛法 | 平台是否追蹤 |
|---|---|---|---|---|
| Labeling（影像標註） | `ANnoTation` | `sidecar/python-engine/plugins/labeling` | **外部資料夾 + 目錄 junction** | ❌ gitignored |
| AI Report | `AI4BI` | `sidecar/python-engine/vendor/AI4BI` | git submodule | ✅ 釘 commit |
| VisualLatent (LV) | `LV` | `sidecar/python-engine/vendor/LV` | git submodule (`uihuang_dev`) | ✅ 釘 commit |

> 為什麼 labeling 用 junction 而非 submodule：讓「平台」與「labeling 外掛」連**實體目錄都分離**——
> labeling 原始碼放在 nativeApp 旁的獨立 clone，nativeApp 樹內不再有它的原始碼，也不釘版本。
> 代價：junction 不進 git，每次 clone／換機要重建一次（見 §3）。

## 3. labeling 的安裝 / 掛載（新機器或重新 clone 後）

```powershell
# 1) 把 labeling 外掛 clone 到 nativeApp 旁邊
git clone https://github.com/hctsaik/ANnoTation.git ..\ANnoTation

# 2) 建立 junction：plugins\labeling -> ..\ANnoTation
scripts\win\link-labeling.bat
#    預設指向 nativeApp 旁的 ..\ANnoTation；可用環境變數覆蓋：
#    set "LABELING_SRC=D:\path\to\ANnoTation"

# 3) labeling 專屬相依
py -3.11 -m pip install -r sidecar\python-engine\plugins\labeling\requirements-labeling.txt
```

- **日後更新 labeling**：到外部 `ANnoTation` 資料夾 `git pull`（junction 即時反映）。
- **缺漏偵測**：`start-*.bat` 啟動前跑 `scripts\win\preflight-submodules.bat`；
  `engine.py` 的 `check_submodules()` 把 labeling 標為 `kind=external`，缺失時提示跑
  `link-labeling.bat`（AI4BI／LV 缺失則提示 `git submodule update --init --recursive`）。
  `scripts\win\verify-setup.ps1` doctor 的「Labeling」區段也會檢查掛載與相依。

## 4. ⚠️ junction 的關鍵約束：不要 `.resolve()` 模組自身路徑

labeling 模組靠**實體目錄深度**反向找 host 共用碼，例如：

```python
_HERE = Path(__file__).parent                       # ✅ 維持在 junction 空間
_HERE.parents[3] / "scripts" / "shared" / "_config_base.py"   # → host python-engine 根
```

若改用 `Path(__file__).resolve()`，`.resolve()` 會把 junction **正規化成外部真實路徑**
（`c:\code\claude\ANnoTation\...`），`parents[N]` 就跳到 `C:\code`、找不到 host 的 `scripts/shared`。

- 規則：**ANnoTation 內凡是以 `__file__` 當「自身位置錨點」者，一律用 `Path(__file__)`，不要 `.resolve()`。**
- 對「資料路徑」（圖片、執行檔、artifact）做 `.resolve()` 不受影響、照常使用。
- 此約束在 submodule 掛法下不存在（同物理樹，`.resolve()` 不會跳出）；改 junction 後才浮現。
  contract 測試 `tests/test_labeling_platform_contract.py` + `test_config_base.py` 會在違反時變紅。

## 5. 平台契約（labeling → host 的單向依賴）

labeling 只能依賴 `core.*` 與 5 個共用檔（`scripts/shared/_config_base.py`、`_help.py`、
`_manifest_db.py`、`ui_components.py`、`tools/db_utils.py`），由
`tests/test_labeling_platform_contract.py` 以 allowlist 鎖死。細節見
[`labeling-independence-plan.md`](labeling-independence-plan.md) §2。
