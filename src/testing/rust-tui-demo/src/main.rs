use std::env;
use std::io::{self, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::thread;
use std::time::{Duration, Instant};

fn start_server(port: u16) -> io::Result<()> {
    let listener = TcpListener::bind(("127.0.0.1", port))?;
    println!("Rust TUI demo server listening on 127.0.0.1:{}", port);
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => handle_connection(stream),
            Err(e) => eprintln!("Connection failed: {}", e),
        }
    }
    Ok(())
}

fn handle_connection(mut stream: TcpStream) {
    let mut buf = [0u8; 1024];
    match stream.read(&mut buf) {
        Ok(0) => {}
        Ok(n) => {
            let request = String::from_utf8_lossy(&buf[..n]);
            if request.contains("#EXIT") {
                let _ = stream.write_all(b"OK:BYE\n##END##\n");
            } else {
                let _ = stream.write_all(b"OK:server mode active\n##END##\n");
            }
        }
        Err(_) => {}
    }
}

fn write_initial_queries(stdout: &mut io::Stdout) -> io::Result<()> {
    stdout.write_all(b"\x1b[?47h")?;
    stdout.write_all(b"\x1b[?2004h")?;
    stdout.write_all(b"\x1b[?2026$p")?;
    stdout.write_all(b"\x1b[?u")?;
    stdout.write_all(b"\x1b[H")?;
    stdout.write_all(b"$qm")?;
    stdout.flush()?;
    Ok(())
}

fn write_cursor_shape_protocol(stdout: &mut io::Stdout) -> io::Result<()> {
    stdout.write_all(b"\x1b[>4;2m")?;
    stdout.write_all(b"\x1b[?1004h")?;
    stdout.write_all(b"\x1b[2 q")?;
    stdout.flush()?;
    Ok(())
}

fn wait_for_sync_suffix(stdin: &mut io::Stdin, suffix: &[u8], timeout_ms: u64) -> io::Result<bool> {
    let mut matched = 0;
    let mut buf = [0u8; 1];
    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    while Instant::now() < deadline {
        match stdin.read(&mut buf) {
            Ok(0) => thread::sleep(Duration::from_millis(10)),
            Ok(_) => {
                if buf[0] == suffix[matched] {
                    matched += 1;
                    if matched == suffix.len() {
                        return Ok(true);
                    }
                } else if buf[0] == suffix[0] {
                    matched = 1;
                } else {
                    matched = 0;
                }
            }
            Err(_) => thread::sleep(Duration::from_millis(10)),
        }
    }
    Ok(false)
}

fn write_empty_buffer_screen(stdout: &mut io::Stdout) -> io::Result<()> {
    stdout.write_all(b"\x1b[38;2;200;211;245m")?;
    stdout.write_all(b"\x1b[48;2;34;36;54m")?;
    stdout.write_all(b"\x1b[H")?;
    stdout.write_all(b"\x1b[200X")?;
    stdout.write_all(b"\x1b[200C~        \r\n")?;
    stdout.write_all(b"~\x1b[K\r\n")?;
    stdout.write_all(b"~\x1b[K\r\n")?;
    stdout.write_all(b"~\x1b[K\r\n")?;
    stdout.write_all(b"\x1b[12;58HEmpty buffer startup screen\x1b[K\r\n")?;
    stdout.write_all(b"\x1b[13;47HThis path should stay visible in a real terminal\x1b[K\r\n")?;
    stdout.write_all(b"\x1b[14;66Htype  :q  to exit\x1b[K\r\n")?;
    stdout.flush()?;
    Ok(())
}

fn write_file_buffer_screen(stdout: &mut io::Stdout) -> io::Result<()> {
    stdout.write_all(b"\x1b[38;2;130;139;184m")?;
    stdout.write_all(b"\x1b[48;2;30;32;48m")?;
    stdout.write_all(b"\x1b[38;2;200;211;245m")?;
    stdout.write_all(b"\x1b[48;2;34;36;54m")?;
    stdout.write_all(b"\x1b[H")?;
    stdout.write_all(b"\x1b[200X")?;
    stdout.write_all(b"\x1b[200C~        \r\n")?;
    stdout.write_all(b"~\x1b[K\r\n")?;
    stdout.write_all(b"~\x1b[K\r\n")?;
    stdout.write_all(b"\x1b[105X")?;
    stdout.write_all(b"\x1b[105Cexample_buffer.txt\x1b[K\r\n")?;
    stdout.write_all(b"0,0-1          All\x1b[K\r\n")?;
    stdout.flush()?;
    Ok(())
}

fn run_empty_buffer_path(stdout: &mut io::Stdout, stdin: &mut io::Stdin) -> io::Result<()> {
    write_initial_queries(stdout)?;
    write_cursor_shape_protocol(stdout)?;
    let sync_ready = wait_for_sync_suffix(stdin, b";2$y", 800)?;
    if sync_ready {
        write_empty_buffer_screen(stdout)?;
    }
    Ok(())
}

fn run_file_buffer_path(stdout: &mut io::Stdout, stdin: &mut io::Stdin) -> io::Result<()> {
    write_initial_queries(stdout)?;
    write_cursor_shape_protocol(stdout)?;
    write_file_buffer_screen(stdout)?;
    let _ = wait_for_sync_suffix(stdin, b"$y", 800)?;
    Ok(())
}

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();

    if args.len() > 1 && args[1] == "--port" {
        let port: u16 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(9999);
        return start_server(port);
    }

    let mut stdout = io::stdout();
    let mut stdin = io::stdin();
    let mode = args.get(1).cloned().unwrap_or_else(|| "empty_buffer_path".to_string());

    if mode == "empty_buffer_path" {
        run_empty_buffer_path(&mut stdout, &mut stdin)?;
    }
    if mode == "file_buffer_path" {
        run_file_buffer_path(&mut stdout, &mut stdin)?;
    }

    thread::sleep(Duration::from_secs(3));
    stdout.write_all(b"\x1b[m")?;
    stdout.flush()?;
    Ok(())
}