//! module 02 單元測試(/pm 擁有,PG 唯讀)。對映 3_Architect_Design/10_module-contracts.md。
//! 純函式層級:不需 Tauri runtime、不需真 engine。

use std::io::{Read, Write};
use std::net::TcpListener;
use std::time::{Duration, Instant};

use cim_light::sidecar;

// AC2.1 — find_free_port 回傳可再次綁定的埠
#[test]
fn test_find_free_port_is_bindable() {
    let p = sidecar::find_free_port().expect("find_free_port");
    assert!(p >= 1024, "ephemeral 埠應 >= 1024,得到 {p}");
    let again = TcpListener::bind(("127.0.0.1", p));
    assert!(again.is_ok(), "埠 {p} 釋放後應可再次綁定");
}

// AC2.2 — spawn argv 與 env(反向稽查:必含 PYTHONUTF8=1)
#[test]
fn test_spawn_args_and_env() {
    let args = sidecar::spawn_args(12345, std::path::Path::new("C:/tmp/logs"));
    assert!(args.contains(&"--control-port".to_string()));
    assert!(args.contains(&"12345".to_string()));
    assert!(args.contains(&"--log-dir".to_string()));

    let env = sidecar::base_env();
    assert!(
        env.iter().any(|(k, v)| k == "PYTHONUTF8" && v == "1"),
        "env 必含 PYTHONUTF8=1(對映 Electron spawnSidecar)"
    );
}

/// 在背景起一個極簡 HTTP server,對任何請求回固定狀態/內容。
fn spawn_mock(status_line: &'static str, body: &'static str) -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            if let Ok(mut s) = stream {
                s.set_read_timeout(Some(Duration::from_millis(500))).ok();
                let mut buf = [0u8; 1024];
                let _ = s.read(&mut buf);
                let resp = format!(
                    "HTTP/1.1 {status_line}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
                let _ = s.write_all(resp.as_bytes());
                let _ = s.flush();
            }
        }
    });
    port
}

// AC2.3 — 健康輪詢:mock 回 ok → Ok（metamorphic：狀態 ok 即就緒）
#[test]
fn test_poll_health_ready_ok() {
    let port = spawn_mock("200 OK", "{\"status\":\"ok\"}");
    let r = sidecar::poll_health_ready(port, Duration::from_secs(3));
    assert!(r.is_ok(), "health=ok 應在逾時內就緒,得到 {r:?}");
}

// AC2.3 — 健康輪詢:mock 恆 503 → Err 且耗時 ≈ timeout（不變量：非 ok 不會誤判就緒）
#[test]
fn test_poll_health_timeout() {
    let port = spawn_mock("503 Service Unavailable", "{}");
    let timeout = Duration::from_millis(800);
    let start = Instant::now();
    let r = sidecar::poll_health_ready(port, timeout);
    let elapsed = start.elapsed();
    assert!(r.is_err(), "health 恆 503 應逾時失敗");
    assert!(elapsed >= timeout, "應等滿 timeout({elapsed:?} < {timeout:?})");
    assert!(elapsed < timeout + Duration::from_millis(800), "不應遠超 timeout({elapsed:?})");
}
