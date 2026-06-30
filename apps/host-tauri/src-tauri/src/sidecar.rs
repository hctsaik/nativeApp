//! module 02 — sidecar-manager
//! 對映 Electron main.js 的 startSidecar…stopSidecar。
//! 純函式(find_free_port / spawn_args / base_env / poll_health_ready)獨立出來供單元測試。

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Emitter, Manager};

/// Tauri 管理狀態:跨指令/執行緒共用 sidecar 生命週期資料。
pub struct AppState {
    pub control_port: Arc<Mutex<Option<u16>>>,
    pub log_dir: Arc<Mutex<PathBuf>>,
    pub child: Arc<Mutex<Option<Child>>>,
    pub stopping: Arc<AtomicBool>,
    pub engine_exe: Arc<Mutex<PathBuf>>,
}

impl AppState {
    pub fn new(engine_exe: PathBuf, log_dir: PathBuf) -> Self {
        Self {
            control_port: Arc::new(Mutex::new(None)),
            log_dir: Arc::new(Mutex::new(log_dir)),
            child: Arc::new(Mutex::new(None)),
            stopping: Arc::new(AtomicBool::new(false)),
            engine_exe: Arc::new(Mutex::new(engine_exe)),
        }
    }
}

// ───────────────────────── 純函式(單元測試對象)─────────────────────────

/// AC2.1 — 綁定 127.0.0.1:0 取系統配發的空閒埠。
pub fn find_free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    Ok(listener.local_addr()?.port())
}

/// AC2.2 — spawn engine 的 argv(必含 control-port/log-dir)。
pub fn spawn_args(port: u16, log_dir: &Path) -> Vec<String> {
    vec![
        "--control-port".into(),
        port.to_string(),
        "--log-dir".into(),
        log_dir.to_string_lossy().into_owned(),
    ]
}

/// AC2.2 — 注入 engine 的最小 env(必含 PYTHONUTF8=1)。
pub fn base_env() -> Vec<(String, String)> {
    vec![("PYTHONUTF8".into(), "1".into())]
}

/// 對 GET /health 判 status==ok。
pub fn check_health(port: u16) -> bool {
    match ureq::get(&format!("http://127.0.0.1:{port}/health"))
        .timeout(Duration::from_millis(800))
        .call()
    {
        Ok(resp) => resp
            .into_json::<serde_json::Value>()
            .ok()
            .and_then(|v| v.get("status").and_then(|s| s.as_str()).map(|s| s == "ok"))
            .unwrap_or(false),
        Err(_) => false,
    }
}

/// AC2.3 — 純健康輪詢(無 child 檢查),供單元測試 mock server。
pub fn poll_health_ready(port: u16, timeout: Duration) -> Result<(), String> {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if check_health(port) {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err("Sidecar readiness timed out".into())
}

// ───────────────────────── 生命週期(整合/E2E 對象)─────────────────────────

fn now_ms() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0)
}

pub fn append_log(log_dir: &Path, msg: &str) {
    let _ = std::fs::create_dir_all(log_dir);
    let line = format!("[{}ms] {}\n", now_ms(), msg);
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join("host.log"))
    {
        let _ = f.write_all(line.as_bytes());
    }
}

fn pipe_to_log(stream: impl Read + Send + 'static, dir: PathBuf, tag: &'static str) {
    std::thread::spawn(move || {
        let reader = BufReader::new(stream);
        for line in reader.lines().map_while(Result::ok) {
            append_log(&dir, &format!("[sidecar {tag}] {line}"));
        }
    });
}

fn spawn_engine(exe: &Path, port: u16, log_dir: &Path) -> Result<Child, String> {
    // 支援兩種 engine:frozen `.exe`(直接執行,對映 Electron packaged)
    // 或 `.py` 原始碼(用 python 跑,對映 Electron dev)。.py 用 CIM_ENGINE_PYTHON 指定直譯器。
    let is_py = exe.extension().map(|e| e.eq_ignore_ascii_case("py")).unwrap_or(false);
    let mut cmd = if is_py {
        let python = std::env::var("CIM_ENGINE_PYTHON").unwrap_or_else(|_| "python".into());
        let mut c = Command::new(python);
        c.arg(exe);
        c
    } else {
        Command::new(exe)
    };
    cmd.args(spawn_args(port, log_dir));
    for (k, v) in base_env() {
        cmd.env(k, v);
    }
    cmd.current_dir(exe.parent().unwrap_or_else(|| Path::new(".")));
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW(對等 Electron windowsHide）
    }
    let mut child = cmd.spawn().map_err(|e| format!("spawn engine failed: {e}"))?;
    if let Some(out) = child.stdout.take() {
        pipe_to_log(out, log_dir.to_path_buf(), "stdout");
    }
    if let Some(err) = child.stderr.take() {
        pipe_to_log(err, log_dir.to_path_buf(), "stderr");
    }
    Ok(child)
}

/// 等待就緒,同時偵測 child 提前 exit(AC2.4)。
fn wait_ready_or_exit(
    child: &Arc<Mutex<Option<Child>>>,
    port: u16,
    timeout: Duration,
) -> Result<(), String> {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if let Some(c) = child.lock().unwrap().as_mut() {
            if let Ok(Some(status)) = c.try_wait() {
                return Err(format!("Sidecar exited before readiness: {status:?}"));
            }
        }
        if check_health(port) {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    Err("Sidecar readiness timed out".into())
}

/// 啟動 sidecar:找埠 → spawn → 等就緒 → 掛崩潰監看。
pub fn start(app: &AppHandle) -> Result<u16, String> {
    let state = app.state::<AppState>();
    state.stopping.store(false, Ordering::SeqCst);

    let port = find_free_port().map_err(|e| e.to_string())?;
    let log_dir = state.log_dir.lock().unwrap().clone();
    std::fs::create_dir_all(&log_dir).ok();
    let exe = state.engine_exe.lock().unwrap().clone();
    if !exe.exists() {
        return Err(format!("engine 不存在:{}(設 CIM_ENGINE_EXE 覆寫)", exe.display()));
    }
    append_log(
        &log_dir,
        &format!("Starting sidecar: {} --control-port {} --log-dir {}", exe.display(), port, log_dir.display()),
    );

    let child = spawn_engine(&exe, port, &log_dir)?;
    *state.child.lock().unwrap() = Some(child);
    *state.control_port.lock().unwrap() = Some(port);

    // frozen engine.exe 首啟需解壓(實測 ~24s),dev 給 60s 餘裕;packaged 給 120s。
    let timeout = Duration::from_secs(if cfg!(debug_assertions) { 60 } else { 120 });
    wait_ready_or_exit(&state.child, port, timeout)?;
    append_log(&log_dir, &format!("Sidecar ready on port {port}"));

    spawn_monitor(app.clone());
    Ok(port)
}

/// AC2.6 — 崩潰自動重啟監看。
fn spawn_monitor(app: AppHandle) {
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_millis(500));
        let state = app.state::<AppState>();
        if state.stopping.load(Ordering::SeqCst) {
            break;
        }
        // None = 仍在執行;Some(code) = 已 exit(code 可能 None)。
        let exited: Option<Option<i32>> = {
            let mut guard = state.child.lock().unwrap();
            match guard.as_mut() {
                Some(c) => match c.try_wait() {
                    Ok(Some(status)) => Some(status.code()),
                    _ => None,
                },
                None => Some(None),
            }
        };
        let code = match exited {
            Some(c) => c,
            None => continue,
        };
        if state.stopping.load(Ordering::SeqCst) {
            break;
        }
        let log_dir = state.log_dir.lock().unwrap().clone();
        append_log(&log_dir, "Sidecar crashed unexpectedly — auto-restarting in 3 s");
        // payload 形狀對齊 portal 解構:{code, signal} / {error}
        let _ = app.emit("sidecar-exited", serde_json::json!({ "code": code, "signal": serde_json::Value::Null }));
        let _ = app.emit("sidecar-restarting", serde_json::json!({}));
        std::thread::sleep(Duration::from_secs(3));
        *state.child.lock().unwrap() = None;
        match start(&app) {
            Ok(_) => {
                let _ = app.emit("sidecar-ready", serde_json::json!({}));
            }
            Err(e) => {
                append_log(&log_dir, &format!("Sidecar auto-restart failed: {e}"));
                let _ = app.emit("sidecar-restart-failed", serde_json::json!({ "error": e }));
            }
        }
        break; // start() 已掛新監看
    });
}

/// AC2.5 — graceful 關閉:POST /shutdown(5s)否則 kill;冪等。
pub fn stop(app: &AppHandle) {
    let state = app.state::<AppState>();
    if state.stopping.swap(true, Ordering::SeqCst) {
        return; // 已在停止 → no-op(冪等)
    }
    let log_dir = state.log_dir.lock().unwrap().clone();
    append_log(&log_dir, "Stopping sidecar");

    let port = *state.control_port.lock().unwrap();
    if let Some(p) = port {
        let _ = ureq::post(&format!("http://127.0.0.1:{p}/shutdown"))
            .timeout(Duration::from_secs(5))
            .call();
    }

    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        {
            let mut guard = state.child.lock().unwrap();
            match guard.as_mut() {
                Some(c) => {
                    if let Ok(Some(_)) = c.try_wait() {
                        *guard = None;
                        break;
                    }
                }
                None => break,
            }
        }
        if Instant::now() >= deadline {
            let mut guard = state.child.lock().unwrap();
            if let Some(c) = guard.as_mut() {
                append_log(&log_dir, "Forcing sidecar kill");
                let _ = c.kill();
            }
            *guard = None;
            break;
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    *state.control_port.lock().unwrap() = None;
}

/// 解析 spike 要對的 engine.exe(env CIM_ENGINE_EXE 覆寫,否則指既有平台的 frozen engine)。
pub fn resolve_engine_exe() -> PathBuf {
    if let Ok(p) = std::env::var("CIM_ENGINE_EXE") {
        return PathBuf::from(p);
    }
    PathBuf::from(r"C:\code\claude\nativeApp\sidecar\python-engine\dist\engine.exe")
}

pub fn resolve_log_dir() -> PathBuf {
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")).join("logs")
}
