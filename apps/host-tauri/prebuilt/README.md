# prebuilt/ — Tauri 殼可執行檔放這裡（**不進 git**）

`cim-light.exe`（Tauri 殼）**不進版控**（見上層 `.gitignore` 的 `prebuilt/*.exe`）。
`start-dev-tauri.bat` 會依序找：`prebuilt\cim-light.exe` →
`src-tauri\target\release\cim-light.exe` → `…\target\debug\cim-light.exe` → 舊 sibling。
只要其中一顆存在就能啟動。

## 怎麼取得這顆 exe

### 非 WDAC 強制的機器（可自己 build）
```powershell
scripts\win\build-shell.bat
# = cargo build --release（apps\host-tauri\src-tauri）→ 複製到 prebuilt\cim-light.exe
```
> 前置：Rust toolchain（rustup）、且 `apps\portal-react\dist` 已建好。
> 要「簽章 release 安裝包」走 `npm --prefix apps\host-tauri run tauri:build`（見 ../SIGNING.md）。

### 本開發機（WDAC 強制，cargo 會被擋）
不能在此 build。到上面那種機器跑 `build-shell.bat`，再把產出的
`cim-light.exe` 複製到本機這個 `prebuilt\` 資料夾即可（既有/複製進來的未簽章 exe
在 WDAC 下跑得起來——見 repo 根 `CLAUDE.md` 的 WDAC 段）。
