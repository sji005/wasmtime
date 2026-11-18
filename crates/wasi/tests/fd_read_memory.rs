//! Boundary regressions through the generated Preview 1 binding.

#![cfg(feature = "p1")]

use wasmtime::{Engine, Linker, Module, Result, Store};
use wasmtime_wasi::p1::add_to_linker_sync;
use wasmtime_wasi::p2::pipe::MemoryInputPipe;
use wasmtime_wasi::{FsPerms, WasiCtxBuilder};

const PAGE: usize = 65536;
const OUTPUT: usize = 16;
const SENTINEL: u8 = 0xa5;

fn fd_read_module(engine: &Engine) -> Result<Module> {
    Module::new(
        engine,
        r#"
        (module
            (import "wasi_snapshot_preview1" "fd_read"
                (func $fd_read (param i32 i32 i32 i32) (result i32)))
            (import "wasi_snapshot_preview1" "path_open"
                (func $path_open (param i32 i32 i32 i32 i32 i64 i64 i32 i32) (result i32)))
            (memory (export "memory") 1)
            (func (export "read") (param i32 i32 i32 i32) (result i32)
                local.get 0
                local.get 1
                local.get 2
                local.get 3
                call $fd_read)
            (func (export "open") (param i32 i32 i32) (result i32)
                (call $path_open (i32.const 3) (i32.const 0) (local.get 0)
                    (local.get 1) (i32.const 0)
                    (i64.const 2) ;; rights::fd_read
                    (i64.const 0)
                    (i32.const 0) (local.get 2))))
        "#,
    )
}

#[test]
fn fd_read_metadata_and_result_boundaries() -> Result<()> {
    let engine = Engine::default();
    let module = fd_read_module(&engine)?;
    let mut linker = Linker::new(&engine);
    add_to_linker_sync(&mut linker, |ctx| ctx)?;

    for (name, stdin, arguments, trap) in [
        (
            "exact-fit destination, short read",
            &b"xy"[..],
            (0, 2, OUTPUT),
            false,
        ),
        (
            "truncated iovec record",
            &b"xy"[..],
            (PAGE - 4, 1, OUTPUT),
            true,
        ),
        ("out of bounds result", &b"xy"[..], (0, 2, PAGE), true),
        (
            "result aliases payload",
            &b"xy"[..],
            (0, 2, PAGE - 4),
            false,
        ),
        ("all buffers empty at EOF", &b""[..], (0, 1, OUTPUT), false),
    ] {
        let ctx = WasiCtxBuilder::new()
            .stdin(MemoryInputPipe::new(stdin))
            .build_p1();
        let mut store = Store::new(&engine, ctx);
        let instance = linker.instantiate(&mut store, &module)?;
        let memory = instance.get_memory(&mut store, "memory").unwrap();
        let read = instance.get_typed_func::<(u32, u32, u32, u32), u32>(&mut store, "read")?;
        let mut expected = vec![SENTINEL; PAGE];
        // Skip the first empty iovec even though its unused buffer starts
        // beyond memory. The second iovec describes its final four bytes.
        expected[0..4].copy_from_slice(&((PAGE + 1) as u32).to_le_bytes());
        expected[4..8].copy_from_slice(&0u32.to_le_bytes());
        expected[8..12].copy_from_slice(&((PAGE - 4) as u32).to_le_bytes());
        expected[12..16].copy_from_slice(&4u32.to_le_bytes());
        memory.write(&mut store, 0, &expected)?;

        let (array, count, output) = arguments;
        let result = read.call(&mut store, (0, array as u32, count, output as u32));
        if trap {
            assert!(result.is_err(), "{name}: {result:?}");
        } else {
            assert_eq!(result?, 0, "{name}");
        }

        if array == 0 && count == 2 {
            expected[PAGE - 4..PAGE - 2].copy_from_slice(b"xy");
        }
        if !trap {
            expected[output..output + 4].copy_from_slice(&(stdin.len() as u32).to_le_bytes());
        }
        assert!(
            memory.data(&store) == expected.as_slice(),
            "{name}: unexpected memory effects"
        );
    }
    Ok(())
}

#[test]
fn fd_read_direct_file_and_worker_boundaries() -> Result<()> {
    let temp = tempfile::tempdir()?;
    let file = "payload";
    std::fs::write(temp.path().join(file), b"xy")?;
    let engine = Engine::default();
    let module = fd_read_module(&engine)?;
    let mut linker = Linker::new(&engine);
    add_to_linker_sync(&mut linker, |ctx| ctx)?;

    for allow_blocking in [true, false] {
        let ctx = WasiCtxBuilder::new()
            .allow_blocking_current_thread(allow_blocking)
            .preopened_dir(temp.path(), ".", FsPerms::ReadOnly)?
            .build_p1();
        let mut store = Store::new(&engine, ctx);
        let instance = linker.instantiate(&mut store, &module)?;
        let memory = instance.get_memory(&mut store, "memory").unwrap();
        let open = instance.get_typed_func::<(u32, u32, u32), u32>(&mut store, "open")?;
        let read = instance.get_typed_func::<(u32, u32, u32, u32), u32>(&mut store, "read")?;

        let path = 32;
        let mut expected = vec![SENTINEL; PAGE];
        expected[path..path + file.len()].copy_from_slice(file.as_bytes());
        expected[0..4].copy_from_slice(&((PAGE - 4) as u32).to_le_bytes());
        expected[4..8].copy_from_slice(&4u32.to_le_bytes());
        memory.write(&mut store, 0, &expected)?;
        assert_eq!(
            open.call(&mut store, (path as u32, file.len() as u32, OUTPUT as u32))?,
            0
        );
        let fd = u32::from_le_bytes(memory.data(&store)[OUTPUT..OUTPUT + 4].try_into().unwrap());
        assert_eq!(read.call(&mut store, (fd, 0, 1, OUTPUT as u32))?, 0);

        expected[OUTPUT..OUTPUT + 4].copy_from_slice(&2u32.to_le_bytes());
        expected[PAGE - 4..PAGE - 2].copy_from_slice(b"xy");
        assert!(
            memory.data(&store) == expected.as_slice(),
            "unexpected memory effects with allow_blocking_current_thread={allow_blocking}"
        );
    }
    Ok(())
}
