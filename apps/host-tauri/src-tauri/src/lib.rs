//! module 01 — app-shell + 全域 wiring
//! 對映 Electron main.js 的 createWindow / app 生命週期。
//! 設計:sidecar 就緒「後」才在主執行緒建立視窗 → portal 載入時 getAppConfig 已能拿到真實 port,
//! 對映 Electron「startSidecar() 完成後才 createWindow()」。

pub mod bridge;
pub mod sidecar;

use std::sync::atomic::Ordering;
use tauri::{Emitter, Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent};

/// module 03 的注入腳本:portal bundle 執行前先定義 window.cimHost。
const SHIM: &str = include_str!("../cimhost-shim.js");

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let state = sidecar::AppState::new(sidecar::resolve_engine_exe(), sidecar::resolve_log_dir());

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            bridge::get_app_config,
            bridge::list_tools,
            bridge::start_tool,
            bridge::start_sheet_tab,
            bridge::stop_tool,
            bridge::get_tool_status,
            bridge::get_runtime_status,
            bridge::get_diagnostics,
            bridge::external_open_xanylabeling,
            bridge::external_open_labeling_tool,
            bridge::external_queue_image,
            bridge::external_get_queue,
            bridge::external_dequeue,
            bridge::renderer_log,
            bridge::restart_sidecar,
            bridge::choose_file,
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            // 背景啟動 sidecar(阻塞在此執行緒,不卡事件迴圈);就緒後回主執行緒建視窗。
            std::thread::spawn(move || {
                let result = sidecar::start(&handle);
                let h2 = handle.clone();
                let _ = handle.run_on_main_thread(move || {
                    match WebviewWindowBuilder::new(&h2, "main", WebviewUrl::App("index.html".into()))
                        .title("CIM Hybrid Edge Platform")
                        .inner_size(1280.0, 820.0)
                        .min_inner_size(960.0, 640.0)
                        .initialization_script(SHIM)
                        .build()
                    {
                        Ok(w) => {
                            let _ = w.maximize();
                            let _ = w.show();
                        }
                        Err(e) => eprintln!("window build failed: {e}"),
                    }
                    match &result {
                        Ok(_) => {
                            let _ = h2.emit("sidecar-ready", ());
                        }
                        Err(e) => {
                            use tauri_plugin_dialog::{DialogExt, MessageDialogKind};
                            h2.dialog()
                                .message(format!("引擎啟動失敗:{e}"))
                                .kind(MessageDialogKind::Error)
                                .title("CIM Hybrid Edge Platform")
                                .show(|_| {});
                        }
                    }
                });
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            // R5 / AC1.4 — 攔截關窗,先 graceful 關 sidecar,再退出,避免孤兒 Python 程序。
            if let WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle().clone();
                let state = app.state::<sidecar::AppState>();
                if !state.stopping.load(Ordering::SeqCst) {
                    api.prevent_close();
                    std::thread::spawn(move || {
                        sidecar::stop(&app);
                        app.exit(0);
                    });
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
