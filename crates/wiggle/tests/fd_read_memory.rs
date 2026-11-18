//! Execution regressions for original dependencies reached by P1 fd_read.
//! These tests do not prove fd_read, its generated caller, or async composition.

use wiggle::{GuestError, GuestMemory, GuestPtr, GuestType};

#[repr(align(8))]
struct Aligned([u8; 32]);

#[test]
fn original_unshared_range_and_copy_boundaries() {
    for start in 0..=40u32 {
        for count in 0..=40u32 {
            let mut bytes = Aligned([0xa5; 32]);
            let mut memory = GuestMemory::Unshared(&mut bytes.0);
            let ptr = GuestPtr::new((start, count));
            let fits = start <= 32 && count <= 32 - start;
            let result = memory.as_slice_mut(ptr);
            assert_eq!(result.is_ok(), fits, "range {start}+{count}");
            if let Ok(Some(slice)) = result {
                assert_eq!(slice.len(), count as usize);
            }
            let source = vec![0x5a; count as usize];
            let result = memory.copy_from_slice(&source, ptr);
            // Original copy_from_slice exits before validation for empty copies.
            assert_eq!(result.is_ok(), fits || count == 0);
            drop(memory);
            for (index, byte) in bytes.0.iter().enumerate() {
                let written = fits && (start as usize..(start + count) as usize).contains(&index);
                assert_eq!(*byte, if written { 0x5a } else { 0xa5 });
            }
        }
    }
}

#[test]
fn original_typed_width_alignment_and_overflow() {
    let mut bytes = Aligned([0; 32]);
    let mut memory = GuestMemory::Unshared(&mut bytes.0);
    memory.write(GuestPtr::new(28), 0x12345678u32).unwrap();
    assert_eq!(memory.read::<u32>(GuestPtr::new(28)).unwrap(), 0x12345678);
    assert!(memory.write(GuestPtr::new(29), 1u32).is_err());
    assert!(matches!(
        memory.read::<u32>(GuestPtr::new(1)),
        Err(GuestError::PtrNotAligned(..))
    ));
    assert!(matches!(
        memory.to_vec::<u64>(GuestPtr::new((0, u32::MAX / 8 + 1))),
        Err(GuestError::PtrOverflow)
    ));
    assert!(
        memory
            .as_slice_mut(GuestPtr::new((u32::MAX, u32::MAX)))
            .is_err()
    );
    // get_range(0..n), as used by fd_read copy-back, retains the selected base.
    let ptr = GuestPtr::<[u8]>::new((20, 12));
    assert_eq!(ptr.get_range(0..12).unwrap().offset(), (20, 12));
    assert!(ptr.get_range(0..13).is_none());
    let mut pointers = GuestPtr::<[u64]>::new((u32::MAX - 7, 2))
        .iter()
        .collect::<Vec<_>>();
    assert!(pointers.remove(0).is_ok());
    assert!(matches!(pointers.remove(0), Err(GuestError::PtrOverflow)));
    assert_eq!(u32::guest_size(), 4);
}

#[cfg(feature = "wasmtime")]
#[test]
fn original_ranges_keep_full_length_and_exact_fit() {
    use wasmtime::{Engine, Memory, MemoryType, Store};
    let engine = Engine::default();
    let mut store = Store::new(&engine, ());
    let memory = Memory::new(&mut store, MemoryType::new(1, None)).unwrap();
    let full_len = memory.data_size(&store);
    let (mut ranges, _) = memory.data_ranges_and_store_data_mut(&mut store);
    assert_eq!(ranges.data_range_mut(full_len..full_len).unwrap().len(), 0);
    assert!(ranges.data_range_mut(full_len + 1..full_len + 1).is_err());
    assert!(ranges.data_range_mut(2..1).is_err());
    let mut guest = GuestMemory::Ranges(ranges);
    let end = full_len as u32;
    guest
        .copy_from_slice(&[1u8, 2, 3, 4], GuestPtr::new((end - 4, 4)))
        .unwrap();
    assert_eq!(
        guest
            .as_slice_mut(GuestPtr::new((0, end)))
            .unwrap()
            .unwrap()
            .len(),
        full_len
    );
    guest.write(GuestPtr::new(end - 4), 42u32).unwrap();
    assert_eq!(guest.read::<u32>(GuestPtr::new(end - 4)).unwrap(), 42);
    assert!(guest.write(GuestPtr::new(end - 3), 42u32).is_err());
    assert!(guest.as_slice_mut(GuestPtr::new((end, 1))).is_err());
    assert!(
        guest
            .as_slice_mut(GuestPtr::new((u32::MAX, u32::MAX)))
            .is_err()
    );
}
