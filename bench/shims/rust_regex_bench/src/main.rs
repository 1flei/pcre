//! Rust regex benchmark shim.
//!
//! Reads a pattern and data file, runs search/match with the Rust
//! regex crate, and prints timing results to stdout.
//!
//! Usage:
//!   rust-regex-bench --pattern PATTERN --data FILE --mode search|match \
//!       --warmup N --repeats N

use std::env;
use std::fs;
use std::time::Instant;

fn main() {
    let args: Vec<String> = env::args().collect();
    let mut pattern = String::new();
    let mut data_file = String::new();
    let mut mode = "search".to_string();
    let mut warmup: usize = 2;
    let mut repeats: usize = 5;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--pattern" => {
                pattern = args[i + 1].clone();
                i += 2;
            }
            "--data" => {
                data_file = args[i + 1].clone();
                i += 2;
            }
            "--mode" => {
                mode = args[i + 1].clone();
                i += 2;
            }
            "--warmup" => {
                warmup = args[i + 1].parse().unwrap_or(2);
                i += 2;
            }
            "--repeats" => {
                repeats = args[i + 1].parse().unwrap_or(5);
                i += 2;
            }
            _ => {
                eprintln!("Unknown argument: {}", args[i]);
                i += 1;
            }
        }
    }

    if pattern.is_empty() || data_file.is_empty() {
        eprintln!("Usage: rust-regex-bench --pattern PATTERN --data FILE [--mode search|match] [--warmup N] [--repeats N]");
        std::process::exit(1);
    }

    let data = match fs::read(&data_file) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("Error reading {}: {}", data_file, e);
            std::process::exit(1);
        }
    };

    let re = match regex::bytes::Regex::new(&pattern) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("Error compiling pattern: {}", e);
            std::process::exit(1);
        }
    };

    // Warmup.
    for _ in 0..warmup {
        if mode == "match" {
            let _ = re.is_match(&data);
        } else {
            let _ = re.find(&data);
        }
    }

    // Measured runs.
    let mut timings: Vec<f64> = Vec::with_capacity(repeats);
    for _ in 0..repeats {
        let start = Instant::now();
        if mode == "match" {
            let _ = re.is_match(&data);
        } else {
            let _ = re.find(&data);
        }
        let elapsed = start.elapsed().as_secs_f64() * 1000.0; // ms
        timings.push(elapsed);
    }

    let best_ms = timings.iter().cloned().fold(f64::INFINITY, f64::min);
    let mean_ms = timings.iter().sum::<f64>() / timings.len() as f64;

    println!("best_ms={:.3} mean_ms={:.3}", best_ms, mean_ms);
}
