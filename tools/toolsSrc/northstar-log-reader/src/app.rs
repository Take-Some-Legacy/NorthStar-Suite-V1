#![allow(unsafe_op_in_unsafe_fn)]

#[cfg(not(windows))]
pub fn run(_initial_url: &str) -> Result<(), String> {
    Err("native LogReader app is currently implemented for Windows only".to_owned())
}

#[cfg(windows)]
mod win32_app {
    use crate::event::NormalizedLogEvent;
    use crate::http;
    use std::ffi::c_void;
    use std::ptr::{null, null_mut};
    use std::sync::mpsc::{self, Receiver, Sender};
    use std::sync::{Arc, Mutex};
    use std::thread;
    use windows_sys::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, RECT, WPARAM};
    use windows_sys::Win32::Graphics::Gdi::{GetStockObject, DEFAULT_GUI_FONT, HBRUSH};
    use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows_sys::Win32::UI::WindowsAndMessaging::*;

    const WM_LOG_EVENT: u32 = WM_APP + 1;
    const WM_STREAM_ENDED: u32 = WM_APP + 2;
    const TIMER_CONNECT_SPINNER: usize = 201;
    const SPINNER_FRAMES: [&str; 4] = ["|", "/", "-", "\\"];
    const ID_URL: i32 = 101;
    const ID_CONNECT: i32 = 102;
    const ID_LOGS: i32 = 103;
    const ID_LEVEL: i32 = 104;
    const ID_SEARCH: i32 = 105;
    const ID_CLEAR: i32 = 106;
    const ID_STATUS: i32 = 107;
    const COLOR_WINDOW: u32 = 5;
    const CB_ADDSTRING: u32 = 0x0143;
    const CB_GETCURSEL: u32 = 0x0147;
    const CB_SETCURSEL: u32 = 0x014E;
    const EM_SETSEL: u32 = 0x00B1;
    const EM_SCROLLCARET: u32 = 0x00B7;

    #[inline]
    fn style(value: i32) -> u32 {
        value as u32
    }

    #[derive(Clone)]
    struct AppStateHandle(Arc<Mutex<AppState>>);

    struct AppState {
        hwnd: HWND,
        url: HWND,
        connect: HWND,
        logs: HWND,
        level: HWND,
        search: HWND,
        clear: HWND,
        status: HWND,
        connected: bool,
        connecting: bool,
        spinner_index: usize,
        events: Vec<NormalizedLogEvent>,
        stop_tx: Option<Sender<()>>,
    }

    impl AppState {
        fn new() -> Self {
            Self {
                hwnd: std::ptr::null_mut(),
                url: std::ptr::null_mut(),
                connect: std::ptr::null_mut(),
                logs: std::ptr::null_mut(),
                level: std::ptr::null_mut(),
                search: std::ptr::null_mut(),
                clear: std::ptr::null_mut(),
                status: std::ptr::null_mut(),
                connected: false,
                connecting: false,
                spinner_index: 0,
                events: Vec::new(),
                stop_tx: None,
            }
        }
    }

    pub fn run(initial_url: &str) -> Result<(), String> {
        // SAFETY: Win32 GUI initialization is process-local; all HWNDs are created and used on this UI thread.
        unsafe { run_win32(initial_url) }
    }

    unsafe fn run_win32(initial_url: &str) -> Result<(), String> {
        let hinstance = GetModuleHandleW(null());
        if hinstance.is_null() {
            return Err("GetModuleHandleW failed".to_owned());
        }

        let class_name = wstr("NorthStarLogReaderWindow");
        let wc = WNDCLASSW {
            style: CS_HREDRAW | CS_VREDRAW,
            lpfnWndProc: Some(wnd_proc),
            cbClsExtra: 0,
            cbWndExtra: 0,
            hInstance: hinstance,
            hIcon: LoadIconW(null_mut(), IDI_APPLICATION),
            hCursor: LoadCursorW(null_mut(), IDC_ARROW),
            hbrBackground: (COLOR_WINDOW + 1) as HBRUSH,
            lpszMenuName: null(),
            lpszClassName: class_name.as_ptr(),
        };

        if RegisterClassW(&wc) == 0 {
            return Err("RegisterClassW failed".to_owned());
        }

        let state = AppStateHandle(Arc::new(Mutex::new(AppState::new())));
        let state_ptr = Box::into_raw(Box::new(state.clone()));
        let title = wstr("North Star LIVE LogReader");

        let hwnd = CreateWindowExW(
            0,
            class_name.as_ptr(),
            title.as_ptr(),
            WS_OVERLAPPEDWINDOW | WS_VISIBLE,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            1180,
            760,
            null_mut(),
            null_mut(),
            hinstance,
            state_ptr as *const c_void,
        );

        if hwnd.is_null() {
            let _ = Box::from_raw(state_ptr);
            return Err("CreateWindowExW failed".to_owned());
        }

        if !initial_url.is_empty() {
            if let Ok(guard) = state.0.lock() {
                set_window_text(guard.url, initial_url);
            }
        }

        let mut msg = std::mem::zeroed::<MSG>();
        while GetMessageW(&mut msg, null_mut(), 0, 0) > 0 {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }

        Ok(())
    }

    unsafe extern "system" fn wnd_proc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
        match msg {
            WM_NCCREATE => {
                let createstruct = lparam as *const CREATESTRUCTW;
                if !createstruct.is_null() {
                    let state_ptr = (*createstruct).lpCreateParams as *mut AppStateHandle;
                    SetWindowLongPtrW(hwnd, GWLP_USERDATA, state_ptr as isize);
                }
                DefWindowProcW(hwnd, msg, wparam, lparam)
            }
            WM_CREATE => {
                create_controls(hwnd);
                0
            }
            WM_SIZE => {
                layout(hwnd);
                0
            }
            WM_COMMAND => {
                let id = (wparam & 0xffff) as i32;
                match id {
                    ID_CONNECT => toggle_connect(hwnd),
                    ID_CLEAR => clear_history(hwnd),
                    ID_LEVEL | ID_SEARCH => refresh_log_text(hwnd),
                    _ => {}
                }
                0
            }
            WM_LOG_EVENT => {
                let event_ptr = lparam as *mut NormalizedLogEvent;
                if !event_ptr.is_null() {
                    let event = *Box::from_raw(event_ptr);
                    if let Some(state) = state(hwnd) {
                        if let Ok(mut guard) = state.0.lock() {
                            if guard.connecting {
                                guard.connecting = false;
                                KillTimer(hwnd, TIMER_CONNECT_SPINNER);
                            }
                            guard.events.push(event);
                            if guard.events.len() > 5000 {
                                guard.events.remove(0);
                            }
                        }
                    }
                    refresh_log_text(hwnd);
                }
                0
            }
            WM_TIMER => {
                if wparam == TIMER_CONNECT_SPINNER {
                    tick_connect_spinner(hwnd);
                    return 0;
                }
                DefWindowProcW(hwnd, msg, wparam, lparam)
            }
            WM_STREAM_ENDED => {
                stream_ended(hwnd, wparam != 0);
                0
            }
            WM_DESTROY => {
                stop_stream(hwnd);
                if let Some(ptr) = raw_state_ptr(hwnd) {
                    let _ = Box::from_raw(ptr);
                    SetWindowLongPtrW(hwnd, GWLP_USERDATA, 0);
                }
                PostQuitMessage(0);
                0
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }

    unsafe fn create_controls(hwnd: HWND) {
        let Some(state) = state(hwnd) else { return; };
        let hinstance = GetModuleHandleW(null());
        let font = GetStockObject(DEFAULT_GUI_FONT);

        let url = child(hwnd, "EDIT", "", WS_BORDER | WS_TABSTOP | style(ES_AUTOHSCROLL), ID_URL, hinstance);
        let connect = child(hwnd, "BUTTON", "Connect", WS_TABSTOP | style(BS_PUSHBUTTON), ID_CONNECT, hinstance);
        let logs = child(
            hwnd,
            "EDIT",
            "",
            WS_BORDER | WS_VSCROLL | style(ES_MULTILINE) | style(ES_AUTOVSCROLL) | style(ES_READONLY),
            ID_LOGS,
            hinstance,
        );
        let level = child(hwnd, "COMBOBOX", "", WS_BORDER | WS_TABSTOP | style(CBS_DROPDOWNLIST), ID_LEVEL, hinstance);
        let search = child(hwnd, "EDIT", "", WS_BORDER | WS_TABSTOP | style(ES_AUTOHSCROLL), ID_SEARCH, hinstance);
        let clear = child(hwnd, "BUTTON", "Clear history logs", WS_TABSTOP | style(BS_PUSHBUTTON), ID_CLEAR, hinstance);
        let status = child(hwnd, "STATIC", "idle", 0, ID_STATUS, hinstance);

        for handle in [url, connect, logs, level, search, clear, status] {
            SendMessageW(handle, WM_SETFONT, font as WPARAM, 1);
        }

        for item in ["TRACE", "DEBUG", "INFO", "WARN", "ERROR"] {
            let text = wstr(item);
            SendMessageW(level, CB_ADDSTRING, 0, text.as_ptr() as LPARAM);
        }
        SendMessageW(level, CB_SETCURSEL, 2, 0);
        set_window_text(search, "");

        if let Ok(mut guard) = state.0.lock() {
            guard.hwnd = hwnd;
            guard.url = url;
            guard.connect = connect;
            guard.logs = logs;
            guard.level = level;
            guard.search = search;
            guard.clear = clear;
            guard.status = status;
        }

        layout(hwnd);
    }

    unsafe fn layout(hwnd: HWND) {
        let Some(state) = state(hwnd) else { return; };
        let mut rect = std::mem::zeroed::<RECT>();
        if GetClientRect(hwnd, &mut rect) == 0 {
            return;
        }
        let width = rect.right - rect.left;
        let height = rect.bottom - rect.top;
        let margin = 12;
        let top_h = 34;
        let bottom_h = 38;
        let gap = 8;
        let button_w = 104;
        let level_w = 150;
        let clear_w = 180;
        let status_w = 170;

        if let Ok(guard) = state.0.lock() {
            MoveWindow(guard.url, margin, margin, width - margin * 2 - button_w - status_w - gap * 2, top_h, 1);
            MoveWindow(guard.connect, width - margin - button_w - status_w - gap, margin, button_w, top_h, 1);
            MoveWindow(guard.status, width - margin - status_w, margin + 8, status_w, 20, 1);

            let log_y = margin + top_h + gap;
            let log_h = height - top_h - bottom_h - margin * 3 - gap * 2;
            MoveWindow(guard.logs, margin, log_y, width - margin * 2, log_h.max(80), 1);

            let bottom_y = height - margin - bottom_h;
            MoveWindow(guard.level, margin, bottom_y, level_w, 160, 1);
            MoveWindow(guard.search, margin + level_w + gap, bottom_y, width - margin * 2 - level_w - clear_w - gap * 2, bottom_h, 1);
            MoveWindow(guard.clear, width - margin - clear_w, bottom_y, clear_w, bottom_h, 1);
        };
    }

    unsafe fn toggle_connect(hwnd: HWND) {
        let Some(state) = state(hwnd) else { return; };
        let connected = state.0.lock().map(|guard| guard.connected).unwrap_or(false);
        if connected {
            stop_stream(hwnd);
            return;
        }

        let url = state.0.lock().map(|guard| get_window_text(guard.url)).unwrap_or_default();
        if url.trim().is_empty() {
            if let Ok(guard) = state.0.lock() {
                set_window_text(guard.status, "enter URL");
            }
            return;
        }
        if !url.starts_with("http://") {
            if let Ok(guard) = state.0.lock() {
                set_window_text(guard.status, "http:// only");
            }
            return;
        }

        let (stop_tx, stop_rx) = mpsc::channel::<()>();
        if let Ok(mut guard) = state.0.lock() {
            guard.connected = true;
            guard.connecting = true;
            guard.spinner_index = 0;
            guard.stop_tx = Some(stop_tx);
            set_window_text(guard.connect, "Disconnect");
            set_window_text(guard.status, "LIVE connecting |");
            SetTimer(hwnd, TIMER_CONNECT_SPINNER, 120, None);
        }

        let target_hwnd = hwnd as isize;
        thread::spawn(move || stream_worker(target_hwnd, url, stop_rx));
    }

    unsafe fn stop_stream(hwnd: HWND) {
        if let Some(state) = state(hwnd) {
            if let Ok(mut guard) = state.0.lock() {
                if let Some(stop_tx) = guard.stop_tx.take() {
                    let _ = stop_tx.send(());
                }
                guard.connected = false;
                guard.connecting = false;
                KillTimer(hwnd, TIMER_CONNECT_SPINNER);
                set_window_text(guard.connect, "Connect");
                set_window_text(guard.status, "disconnected");
            }
        }
    }

    fn stream_worker(hwnd_value: isize, url: String, stop_rx: Receiver<()>) {
        let hwnd = hwnd_value as HWND;
        let result = http::stream_http_events(&url, None, |event| {
            if stop_rx.try_recv().is_ok() {
                return Err("stream stopped".to_owned());
            }
            let boxed = Box::new(event.clone());
            let ptr = Box::into_raw(boxed);
            // SAFETY: ptr is converted back to Box in WM_LOG_EVENT handler on the UI thread.
            unsafe { PostMessageW(hwnd, WM_LOG_EVENT, 0, ptr as LPARAM) };
            Ok(())
        });

        let failed = result.is_err();
        // SAFETY: posts a completion notification to the UI thread; no borrowed data crosses threads.
        unsafe { PostMessageW(hwnd, WM_STREAM_ENDED, usize::from(failed), 0) };
    }

    unsafe fn tick_connect_spinner(hwnd: HWND) {
        if let Some(state) = state(hwnd) {
            if let Ok(mut guard) = state.0.lock() {
                if !guard.connected || !guard.connecting {
                    KillTimer(hwnd, TIMER_CONNECT_SPINNER);
                    return;
                }
                let frame = SPINNER_FRAMES[guard.spinner_index % SPINNER_FRAMES.len()];
                guard.spinner_index = guard.spinner_index.wrapping_add(1);
                set_window_text(guard.status, &format!("LIVE connecting {frame}"));
            }
        }
    }

    unsafe fn stream_ended(hwnd: HWND, failed: bool) {
        if let Some(state) = state(hwnd) {
            if let Ok(mut guard) = state.0.lock() {
                if !guard.connected {
                    return;
                }
                guard.connected = false;
                guard.connecting = false;
                guard.stop_tx = None;
                KillTimer(hwnd, TIMER_CONNECT_SPINNER);
                set_window_text(guard.connect, "Connect");
                if failed {
                    set_window_text(guard.status, "stream ended");
                } else {
                    set_window_text(guard.status, "disconnected");
                }
            }
        }
    }

    unsafe fn clear_history(hwnd: HWND) {
        if let Some(state) = state(hwnd) {
            if let Ok(mut guard) = state.0.lock() {
                guard.events.clear();
                set_window_text(guard.logs, "");
                set_window_text(guard.status, "history cleared");
            }
        }
    }

    unsafe fn refresh_log_text(hwnd: HWND) {
        let Some(state) = state(hwnd) else { return; };
        if let Ok(guard) = state.0.lock() {
            let min_level = selected_level(guard.level);
            let query = get_window_text(guard.search).to_lowercase();
            let mut rendered = String::new();
            let mut visible = 0usize;
            for event in guard.events.iter() {
                if level_rank(&event.level) < level_rank(&min_level) {
                    continue;
                }
                let haystack = format!("{} {} {} {} {}", event.timestamp, event.level, event.target, event.event_id, event.message).to_lowercase();
                if !query.is_empty() && !haystack.contains(&query) {
                    continue;
                }
                visible += 1;
                rendered.push_str(&format!(
                    "{} {:>5} {:<36} {}\r\n",
                    event.timestamp,
                    event.level,
                    truncate(&event.target, 36),
                    event.message.replace('\n', " ")
                ));
            }
            set_window_text(guard.logs, &rendered);
            set_window_text(guard.status, &format!("{visible}/{} visible", guard.events.len()));
            let len = GetWindowTextLengthW(guard.logs);
            SendMessageW(guard.logs, EM_SETSEL, len as WPARAM, len as LPARAM);
            SendMessageW(guard.logs, EM_SCROLLCARET, 0, 0);
        };
    }

    unsafe fn selected_level(level_hwnd: HWND) -> String {
        match SendMessageW(level_hwnd, CB_GETCURSEL, 0, 0) as i32 {
            0 => "TRACE".to_owned(),
            1 => "DEBUG".to_owned(),
            2 => "INFO".to_owned(),
            3 => "WARN".to_owned(),
            4 => "ERROR".to_owned(),
            _ => "INFO".to_owned(),
        }
    }

    fn level_rank(level: &str) -> u8 {
        match level {
            "ERROR" | "Error" | "error" => 5,
            "WARN" | "Warn" | "warn" => 4,
            "INFO" | "Info" | "info" => 3,
            "DEBUG" | "Debug" | "debug" => 2,
            "TRACE" | "Trace" | "trace" => 1,
            _ => 3,
        }
    }

    fn truncate(value: &str, width: usize) -> String {
        let chars: Vec<char> = value.chars().collect();
        if chars.len() <= width {
            return value.to_owned();
        }
        let mut out = chars.into_iter().take(width.saturating_sub(1)).collect::<String>();
        out.push('…');
        out
    }

    unsafe fn child(hwnd: HWND, class: &str, text: &str, style: u32, id: i32, hinstance: HINSTANCE) -> HWND {
        let class = wstr(class);
        let text = wstr(text);
        CreateWindowExW(
            0,
            class.as_ptr(),
            text.as_ptr(),
            WS_CHILD | WS_VISIBLE | style,
            0,
            0,
            10,
            10,
            hwnd,
            id as isize as _,
            hinstance,
            null(),
        )
    }

    unsafe fn state(hwnd: HWND) -> Option<AppStateHandle> {
        raw_state_ptr(hwnd).map(|ptr| (*ptr).clone())
    }

    unsafe fn raw_state_ptr(hwnd: HWND) -> Option<*mut AppStateHandle> {
        let ptr = GetWindowLongPtrW(hwnd, GWLP_USERDATA) as *mut AppStateHandle;
        if ptr.is_null() { None } else { Some(ptr) }
    }

    unsafe fn set_window_text(hwnd: HWND, text: &str) {
        let text = wstr(text);
        SetWindowTextW(hwnd, text.as_ptr());
    }

    unsafe fn get_window_text(hwnd: HWND) -> String {
        let len = GetWindowTextLengthW(hwnd);
        if len <= 0 {
            return String::new();
        }
        let mut buf = vec![0u16; len as usize + 1];
        let read = GetWindowTextW(hwnd, buf.as_mut_ptr(), buf.len() as i32);
        String::from_utf16_lossy(&buf[..read as usize])
    }

    fn wstr(value: &str) -> Vec<u16> {
        value.encode_utf16().chain(std::iter::once(0)).collect()
    }
}

#[cfg(windows)]
pub fn run(initial_url: &str) -> Result<(), String> {
    win32_app::run(initial_url)
}
