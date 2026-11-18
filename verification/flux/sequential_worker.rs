//! Sequential experiment derived from fd_read's file worker.
//! This is not the original hostcall or a model of task scheduling/cancellation.

#![cfg_attr(flux, feature(allocator_api))]

#[cfg(flux)]
extern crate flux_core;
#[cfg(flux)]
extern crate flux_rs;
#[cfg(flux)]
mod sequential_vec_specs;

#[cfg(unix)]
use std::os::unix::fs::FileExt;
#[cfg(windows)]
use std::os::windows::fs::FileExt;
use std::{fs::File, io};

// Linux uses the same primitive as filesystem/unix.rs. The Windows branch is
// solely for native execution checks; it is outside the Linux Flux experiment.
#[cfg_attr(flux, flux::sig(fn(&File, &mut [u8][@n], u64) -> Result<usize{v: v <= n}, io::Error>))]
fn read_at(file: &File, buffer: &mut [u8], position: u64) -> io::Result<usize> {
    #[cfg(unix)]
    {
        file.read_at(buffer, position)
    }
    #[cfg(windows)]
    {
        file.seek_read(buffer, position)
    }
}

// No dummy result and no extra runtime bound check: retain the actual read
// result and the original worker's truncate operation. The postcondition is
// an obligation to prove, not an assumed contract on an unchecked local body.
#[cfg_attr(flux, flux::sig(fn(&File, capacity: usize, u64) -> Result<Vec<u8>{v: v.len <= capacity}, io::Error>))]
pub fn read_on_sync_worker(file: &File, capacity: usize, position: u64) -> io::Result<Vec<u8>> {
    let mut buffer = vec![0; capacity];
    let count = read_at(file, &mut buffer, position)?;
    buffer.truncate(count);
    Ok(buffer)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::Write,
        path::PathBuf,
        sync::atomic::{AtomicUsize, Ordering},
    };

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            static NEXT: AtomicUsize = AtomicUsize::new(0);
            let path = std::env::temp_dir().join(format!(
                "flux-sequential-worker-{}-{}-{}.tmp",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos(),
                NEXT.fetch_add(1, Ordering::Relaxed),
            ));
            let mut file = std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&path)
                .unwrap();
            file.write_all(b"abcdef").unwrap();
            Self(path)
        }
        fn reader(&self) -> File {
            File::open(&self.0).unwrap()
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_file(&self.0);
        }
    }

    #[test]
    fn exact_read_respects_position() {
        let fixture = Fixture::new();
        assert_eq!(
            read_on_sync_worker(&fixture.reader(), 3, 2).unwrap(),
            b"cde"
        );
    }

    #[test]
    fn short_read_returns_only_initialized_result_bytes() {
        let fixture = Fixture::new();
        assert_eq!(read_on_sync_worker(&fixture.reader(), 8, 4).unwrap(), b"ef");
    }

    #[test]
    fn eof_and_zero_capacity_return_empty_buffers() {
        let fixture = Fixture::new();
        assert!(
            read_on_sync_worker(&fixture.reader(), 4, 6)
                .unwrap()
                .is_empty()
        );
        assert!(
            read_on_sync_worker(&fixture.reader(), 0, 0)
                .unwrap()
                .is_empty()
        );
    }

    #[test]
    fn read_failure_is_propagated() {
        let fixture = Fixture::new();
        let write_only = std::fs::OpenOptions::new()
            .write(true)
            .open(&fixture.0)
            .unwrap();
        assert!(read_on_sync_worker(&write_only, 4, 0).is_err());
    }
}
