//! Desktop Pet — Tauri 2 入口
//!
//! 职责:
//!   1. 启动 Python 后端 (uvicorn) 作为子进程
//!   2. 退出时杀掉后端进程
//!   3. 系统托盘: [打开控制台] [退出]
//!   4. 鼠标穿透: 角色外穿透到桌面, 角色上可交互
//!
//! 穿透机制 (混合模式):
//!   - 默认不穿透: 前端通过 mousemove + gl.readPixels 检测像素透明度
//!   - 鼠标离开角色 → 前端开启穿透 → 同时触发 Rust 轮询线程
//!   - 轮询线程每 80ms 向光标位置发 "check-pixel" 事件给前端
//!   - 前端检测像素 alpha, 通过 report_alpha 命令回传
//!   - 轮询线程收到 alpha > 阈值 → 关闭穿透 → 停止轮询

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Emitter, Manager};

/// 前端调用: 切换窗口的鼠标穿透状态。
#[tauri::command]
fn set_click_through(window: tauri::WebviewWindow, ignore: bool) {
    let _ = window.set_ignore_cursor_events(ignore);
}

/// 前端调用: 鼠标离开角色后启动轮询, 让 Rust 在穿透状态下检测光标是否回到角色上。
#[tauri::command]
fn start_click_through_polling(state: tauri::State<ClickThroughState>) {
    state.polling_active.store(true, Ordering::Relaxed);
}

/// 前端调用: 回传像素透明度检测结果 (由轮询线程的 check-pixel 事件触发)。
#[tauri::command]
fn report_alpha(state: tauri::State<ClickThroughState>, alpha: u8) {
    state.latest_alpha.store(alpha, Ordering::Relaxed);
    state.alpha_ready.store(true, Ordering::Relaxed);
}

/// 鼠标穿透状态: Rust 轮询线程和前端命令共享。
struct ClickThroughState {
    /// 前端最新回传的像素 alpha (0~255)
    latest_alpha: AtomicU8,
    /// 前端是否已回传结果
    alpha_ready: AtomicBool,
    /// 轮询线程是否应继续运行
    polling_active: AtomicBool,
}

/// 托管状态: 持有 Python 后端子进程, 退出时 kill。
struct BackendProcess(Mutex<Option<Child>>);

/// 像素透明度阈值: alpha > 此值 = 鼠标在角色上
const ALPHA_THRESHOLD: u8 = 10;
/// 轮询间隔 (ms)
const POLL_INTERVAL_MS: u64 = 80;

fn main() {
    let state = Arc::new(ClickThroughState {
        latest_alpha: AtomicU8::new(0),
        alpha_ready: AtomicBool::new(false),
        polling_active: AtomicBool::new(false),
    });

    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .manage(state.clone())
        .setup(move |app| {
            // ── 1. 启动 Python 后端 ─────────────────────────────
            let backend_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join("..")
                .join("backend")
                .canonicalize()
                .expect("找不到 backend/ 目录");

            let uv_path = which_uv();
            let child = Command::new(&uv_path)
                .args([
                    "run", "uvicorn", "app.main:app",
                    "--host", "127.0.0.1", "--port", "8000",
                ])
                .current_dir(&backend_dir)
                .spawn()
                .expect("启动 Python 后端失败");

            println!("[desktop-pet] Python 后端已启动 (pid: {})", child.id());
            app.state::<BackendProcess>()
                .0.lock().unwrap()
                .replace(child);

            // ── 2. 系统托盘 ─────────────────────────────────────
            let show_console = MenuItem::with_id(app, "show_console", "打开控制台", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_console, &quit])?;

            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .tooltip("Desktop Pet")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show_console" => {
                        if let Some(win) = app.get_webview_window("console") {
                            let _ = win.show();
                            let _ = win.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            // ── 3. 启动鼠标穿透轮询线程 ────────────────────────
            // 只在 polling_active = true 时才实际检测 (由前端触发)
            let handle = app.handle().clone();
            let poll_state = state.clone();
            thread::spawn(move || {
                loop {
                    thread::sleep(Duration::from_millis(POLL_INTERVAL_MS));

                    if !poll_state.polling_active.load(Ordering::Relaxed) {
                        continue;
                    }

                    // 获取当前光标屏幕坐标
                    let Ok(cursor_pos) = handle.cursor_position() else {
                        continue;
                    };

                    // 检查光标是否在 pet 窗口范围内
                    let Some(pet_win) = handle.get_webview_window("pet") else {
                        continue;
                    };

                    let Ok(win_pos) = pet_win.outer_position() else {
                        continue;
                    };
                    let Ok(win_size) = pet_win.outer_size() else {
                        continue;
                    };

                    // 计算光标在窗口内的相对坐标
                    let local_x = cursor_pos.x - win_pos.x as f64;
                    let local_y = cursor_pos.y - win_pos.y as f64;

                    if local_x < 0.0
                        || local_y < 0.0
                        || local_x >= win_size.width as f64
                        || local_y >= win_size.height as f64
                    {
                        // 光标在窗口外 → 保持穿透
                        continue;
                    }

                    // 向 pet 窗口前端发事件, 请求检测像素 alpha
                    poll_state.alpha_ready.store(false, Ordering::Relaxed);
                    let _ = handle.emit_to(
                        pet_win.label(),
                        "check-pixel",
                        serde_json::json!({ "x": local_x, "y": local_y }),
                    );

                    // 等前端回传 (最多 50ms, 比轮询间隔短)
                    for _ in 0..10 {
                        if poll_state.alpha_ready.load(Ordering::Relaxed) {
                            break;
                        }
                        thread::sleep(Duration::from_millis(5));
                    }

                    if poll_state.alpha_ready.load(Ordering::Relaxed) {
                        let alpha = poll_state.latest_alpha.load(Ordering::Relaxed);

                        if alpha > ALPHA_THRESHOLD {
                            // 光标在角色上 → 关闭穿透
                            let _ = pet_win.set_ignore_cursor_events(false);
                            // 停止轮询, 前端接管检测
                            poll_state.polling_active.store(false, Ordering::Relaxed);
                        }
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "console" {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            set_click_through,
            start_click_through_polling,
            report_alpha,
        ])
        .build(tauri::generate_context!())
        .expect("构建 Tauri 应用失败")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                let state = app_handle.state::<BackendProcess>();
                let child = state.0.lock().unwrap().take();
                if let Some(mut child) = child {
                    println!("[desktop-pet] 正在关闭 Python 后端...");
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}

fn which_uv() -> String {
    let candidates = [
        PathBuf::from(r"C:\Users\Lenovo\.local\bin\uv.exe"),
        PathBuf::from(r"C:\Users\Lenovo\.cargo\bin\uv.exe"),
    ];
    for path in &candidates {
        if path.exists() {
            return path.to_string_lossy().to_string();
        }
    }
    "uv".to_string()
}
