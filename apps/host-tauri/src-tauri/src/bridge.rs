//! module 03 — cimhost-bridge(Rust 端)
//! 對映 Electron preload.js 暴露的 window.cimHost 各方法 → Tauri command。
//! 多數方法把呼叫轉發成 HTTP 打 127.0.0.1:<control_port>(engine FastAPI)。

use serde_json::{json, Value};
use std::path::Path;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, State};

use crate::sidecar::{self, AppState};

const MOCK_JWT: &str = "mock.jwt.token";

// ───────────────────────── HTTP 轉發 helper ─────────────────────────

fn base_url(state: &State<AppState>) -> Result<String, String> {
    let port = state.control_port.lock().unwrap().ok_or("sidecar not ready")?;
    Ok(format!("http://127.0.0.1:{port}"))
}

fn parse(resp: ureq::Response) -> Result<Value, String> {
    resp.into_json::<Value>().map_err(|e| e.to_string())
}

fn get_json(state: &State<AppState>, path: &str) -> Result<Value, String> {
    let url = format!("{}{}", base_url(state)?, path);
    parse(ureq::get(&url).timeout(Duration::from_secs(30)).call().map_err(|e| e.to_string())?)
}

fn post_json(state: &State<AppState>, path: &str, body: Value) -> Result<Value, String> {
    let url = format!("{}{}", base_url(state)?, path);
    parse(ureq::post(&url).timeout(Duration::from_secs(30)).send_json(body).map_err(|e| e.to_string())?)
}

fn delete_json(state: &State<AppState>, path: &str) -> Result<Value, String> {
    let url = format!("{}{}", base_url(state)?, path);
    parse(ureq::delete(&url).timeout(Duration::from_secs(30)).call().map_err(|e| e.to_string())?)
}

fn enc(s: &str) -> String {
    urlencoding::encode(s).into_owned()
}

// ───────────────────────── 純轉發 command ─────────────────────────

#[tauri::command]
pub fn list_tools(state: State<AppState>) -> Result<Value, String> {
    get_json(&state, "/tools")
}

#[tauri::command]
pub fn start_tool(state: State<AppState>, tool_id: String) -> Result<Value, String> {
    post_json(&state, &format!("/tools/{}/start", enc(&tool_id)), json!({}))
}

#[tauri::command]
pub fn start_sheet_tab(state: State<AppState>, plugin_id: String) -> Result<Value, String> {
    post_json(&state, &format!("/tools/active/sheet-tab/{}/start", enc(&plugin_id)), json!({}))
}

#[tauri::command]
pub fn stop_tool(state: State<AppState>) -> Result<Value, String> {
    post_json(&state, "/tools/stop", json!({}))
}

#[tauri::command]
pub fn get_tool_status(state: State<AppState>) -> Result<Value, String> {
    get_json(&state, "/tools/active/status")
}

#[tauri::command]
pub fn get_runtime_status(state: State<AppState>) -> Result<Value, String> {
    get_json(&state, "/runtime")
}

#[tauri::command]
pub fn get_diagnostics(state: State<AppState>) -> Result<Value, String> {
    get_json(&state, "/diagnostics")
}

#[tauri::command]
pub fn external_open_xanylabeling(state: State<AppState>, image_url: String, metadata: Option<Value>) -> Result<Value, String> {
    post_json(&state, "/external/open-xanylabeling", json!({ "image_url": image_url, "metadata": metadata.unwrap_or(json!({})) }))
}

#[tauri::command]
pub fn external_open_labeling_tool(state: State<AppState>, tool: Option<String>, image_url: String, metadata: Option<Value>) -> Result<Value, String> {
    post_json(&state, "/external/open-labeling-tool", json!({ "tool": tool.unwrap_or_else(|| "x-anylabeling".into()), "image_url": image_url, "metadata": metadata.unwrap_or(json!({})) }))
}

#[tauri::command]
pub fn external_queue_image(state: State<AppState>, image_url: String, metadata: Option<Value>) -> Result<Value, String> {
    post_json(&state, "/external/queue-image", json!({ "image_url": image_url, "metadata": metadata.unwrap_or(json!({})) }))
}

#[tauri::command]
pub fn external_get_queue(state: State<AppState>) -> Result<Value, String> {
    get_json(&state, "/external/queue")
}

#[tauri::command]
pub fn external_dequeue(state: State<AppState>, item_id: String) -> Result<Value, String> {
    delete_json(&state, &format!("/external/queue/{}", enc(&item_id)))
}

// ───────────────────────── 原生 command ─────────────────────────

/// AC3.3 — 回傳 portal 啟動所需設定。
#[tauri::command]
pub fn get_app_config(state: State<AppState>) -> Result<Value, String> {
    let port = *state.control_port.lock().unwrap();
    let url = port.map(|p| format!("http://127.0.0.1:{p}")).unwrap_or_default();
    let log_dir = state.log_dir.lock().unwrap().to_string_lossy().into_owned();
    let dev_mode = std::env::var("CIM_DEV_MODE").map(|v| v.trim() != "0").unwrap_or(true);
    Ok(json!({
        "sidecarControlUrl": url,
        "mockJwt": MOCK_JWT,
        "enterpriseAppUrl": "",
        "allowedOrigins": ["*"],
        "logDir": log_dir,
        "devMode": dev_mode,
    }))
}

/// 對映 ipcMain.on("renderer-log") — 寫進 host log。
#[tauri::command]
pub fn renderer_log(state: State<AppState>, level: String, message: String) -> Result<(), String> {
    let log_dir = state.log_dir.lock().unwrap().clone();
    sidecar::append_log(&log_dir, &format!("[renderer:{level}] {message}"));
    Ok(())
}

/// 對映 restart-sidecar:停 → 起。
#[tauri::command]
pub async fn restart_sidecar(app: AppHandle) -> Result<(), String> {
    sidecar::stop(&app);
    let app2 = app.clone();
    tauri::async_runtime::spawn_blocking(move || sidecar::start(&app2))
        .await
        .map_err(|e| e.to_string())??;
    let _ = app.emit("sidecar-ready", ());
    Ok(())
}

/// AC3.5 — 原生檔案對話框 → 選到的路徑 POST /selected-paths。
#[tauri::command]
pub async fn choose_file(app: AppHandle, options: Option<Value>) -> Result<Value, String> {
    use tauri_plugin_dialog::DialogExt;

    let want_dir = options
        .as_ref()
        .and_then(|o| o.get("properties"))
        .and_then(|p| p.as_array())
        .map(|a| a.iter().any(|v| v.as_str() == Some("openDirectory")))
        .unwrap_or(false);

    let (tx, rx) = std::sync::mpsc::channel::<Vec<String>>();
    let builder = app.dialog().file();
    if want_dir {
        builder.pick_folders(move |sel| {
            let paths = sel.unwrap_or_default().into_iter().map(|p| p.to_string()).collect();
            let _ = tx.send(paths);
        });
    } else {
        builder.pick_files(move |sel| {
            let paths = sel.unwrap_or_default().into_iter().map(|p| p.to_string()).collect();
            let _ = tx.send(paths);
        });
    }

    let paths = tauri::async_runtime::spawn_blocking(move || rx.recv().unwrap_or_default())
        .await
        .map_err(|e| e.to_string())?;

    if paths.is_empty() {
        return Ok(json!({ "canceled": true, "paths": [] }));
    }

    // 把選取路徑回送 engine(對映 Electron 的 POST /selected-paths）
    let state = app.state::<AppState>();
    if let Ok(port) = base_url_from(&state) {
        let _ = ureq::post(&format!("{port}/selected-paths"))
            .timeout(Duration::from_secs(10))
            .send_json(json!({ "paths": paths }));
    }
    Ok(json!({ "canceled": false, "paths": paths }))
}

fn base_url_from(state: &State<AppState>) -> Result<String, String> {
    let port = state.control_port.lock().unwrap().ok_or("sidecar not ready")?;
    Ok(format!("http://127.0.0.1:{port}"))
}

/// 給整合測試用:確認 engine.exe 路徑解析。
pub fn engine_exists() -> bool {
    Path::new(&sidecar::resolve_engine_exe()).exists()
}
