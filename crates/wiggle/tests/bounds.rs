use wiggle::{GuestError, GuestMemory, GuestPtr};

#[test]
fn guest_buffer_edges() {
    let mut bytes = [0; 16];
    let mut memory = GuestMemory::Unshared(&mut bytes);
    let exact = GuestPtr::<u8>::new(12).as_array(4);
    assert_eq!(memory.as_slice(exact).unwrap().unwrap().len(), 4);
    memory.as_slice_mut(exact).unwrap().unwrap().fill(7);
    assert_eq!(memory.as_slice(exact).unwrap().unwrap(), &[7; 4]);

    let empty_at_end = GuestPtr::<u8>::new(16).as_array(0);
    assert!(memory.as_slice(empty_at_end).unwrap().unwrap().is_empty());

    for (start, len) in [(12, 5), (17, 0), (u32::MAX, 1)] {
        let pointer = GuestPtr::<u8>::new(start).as_array(len);
        assert!(matches!(
            memory.as_slice(pointer),
            Err(GuestError::PtrOutOfBounds(_) | GuestError::PtrOverflow)
        ));
        assert!(matches!(
            memory.as_slice_mut(pointer),
            Err(GuestError::PtrOutOfBounds(_) | GuestError::PtrOverflow)
        ));
    }
}

#[test]
fn element_count_overflow_is_rejected() {
    let mut bytes = [0; 16];
    let memory = GuestMemory::Unshared(&mut bytes);
    let pointer = GuestPtr::<u64>::new(0).as_array(u32::MAX);
    assert!(matches!(
        memory.to_vec(pointer),
        Err(GuestError::PtrOverflow)
    ));
}

#[cfg(feature = "wasmtime")]
#[test]
fn ranges_memory_checks_typed_copy_destination() {
    use wasmtime::{Engine, Memory, MemoryType, Store};

    let engine = Engine::default();
    let mut store = Store::new(&engine, ());
    let memory = Memory::new(&mut store, MemoryType::new(1, None)).unwrap();
    let (ranges, _) = memory.data_ranges_and_store_data_mut(&mut store);
    let mut guest = GuestMemory::Ranges(ranges);
    let last_word = GuestPtr::<u32>::new(65532).as_array(1);
    guest.copy_from_slice(&[42], last_word).unwrap();
    assert_eq!(guest.to_vec(last_word).unwrap(), vec![42]);

    let past_end = GuestPtr::<u32>::new(65532).as_array(2);
    assert!(matches!(
        guest.copy_from_slice(&[1, 2], past_end),
        Err(GuestError::PtrOutOfBounds(_))
    ));
}
