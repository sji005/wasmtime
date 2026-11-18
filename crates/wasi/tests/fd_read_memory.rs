//! Boundary regressions through the generated Preview 1 binding.

#![cfg(feature = "p1")]

use wasmtime::{Engine, Linker, Module, Result, Store};
use wasmtime_wasi::WasiCtxBuilder;
use wasmtime_wasi::p1::add_to_linker_sync;
use wasmtime_wasi::p2::pipe::MemoryInputPipe;

const PAGE: usize = 65536;
const OUTPUT: usize = 16;
const SENTINEL: u8 = 0xa5;

#[test]
fn fd_read_metadata_and_result_boundaries() -> Result<()> {
    let engine = Engine::default();
    let module = Module::new(
        &engine,
        r#"
        (module
            (import "wasi_snapshot_preview1" "fd_read"
                (func $fd_read (param i32 i32 i32 i32) (result i32)))
            (memory (export "memory") 1)
            (func (export "read") (param i32 i32 i32) (result i32)
                i32.const 0
                local.get 0
                local.get 1
                local.get 2
                call $fd_read))
        "#,
    )?;
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
        ("all buffers empty at EOF", &b""[..], (0, 1, OUTPUT), false),
    ] {
        let ctx = WasiCtxBuilder::new()
            .stdin(MemoryInputPipe::new(stdin))
            .build_p1();
        let mut store = Store::new(&engine, ctx);
        let instance = linker.instantiate(&mut store, &module)?;
        let memory = instance.get_memory(&mut store, "memory").unwrap();
        let read = instance.get_typed_func::<(u32, u32, u32), u32>(&mut store, "read")?;
        let mut expected = vec![SENTINEL; PAGE];
        // Skip the first empty iovec even though its unused buffer starts
        // beyond memory. The second iovec describes its final four bytes.
        expected[0..4].copy_from_slice(&((PAGE + 1) as u32).to_le_bytes());
        expected[4..8].copy_from_slice(&0u32.to_le_bytes());
        expected[8..12].copy_from_slice(&((PAGE - 4) as u32).to_le_bytes());
        expected[12..16].copy_from_slice(&4u32.to_le_bytes());
        memory.write(&mut store, 0, &expected)?;

        let (array, count, output) = arguments;
        let result = read.call(&mut store, (array as u32, count, output as u32));
        if trap {
            assert!(result.is_err(), "{name}: {result:?}");
        } else {
            assert_eq!(result?, 0, "{name}");
        }

        if array == 0 && count == 2 {
            expected[PAGE - 4..PAGE - 2].copy_from_slice(b"xy");
        }
        if !trap {
            expected[OUTPUT..OUTPUT + 4].copy_from_slice(&(stdin.len() as u32).to_le_bytes());
        }
        assert!(
            memory.data(&store) == expected.as_slice(),
            "{name}: unexpected memory effects"
        );
    }
    Ok(())
}
