// 正式版隱藏 console 視窗(對映 Electron 無主控台);dev 保留以看 log。
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    cim_light::run()
}
