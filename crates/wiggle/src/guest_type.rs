use crate::{GuestError, GuestMemory, GuestPtr, Region};
use flux_rs::no_panic;
use std::cell::UnsafeCell;
use std::mem;
use std::sync::atomic::{
    AtomicI8, AtomicI16, AtomicI32, AtomicI64, AtomicU8, AtomicU16, AtomicU32, AtomicU64, Ordering,
};

/// A trait for types which are used to report errors. Each type used in the
/// first result position of an interface function is used, by convention, to
/// indicate whether the function was successful and subsequent results are valid,
/// or whether an error occurred. This trait allows wiggle to return the correct
/// value when the interface function's idiomatic Rust method returns
/// `Ok(<rest of return values>)`.
pub trait GuestErrorType {
    fn success() -> Self;
}

/// A trait for types that are intended to be pointees in `GuestPtr<T>`.
///
/// This trait abstracts how to read/write information from the guest memory, as
/// well as how to offset elements in an array of guest memory. This layer of
/// abstraction allows the guest representation of a type to be different from
/// the host representation of a type, if necessary. It also allows for
/// validation when reading/writing.
pub trait GuestType: Sized {
    /// Returns the size, in bytes, of this type in the guest memory.
    ///
    /// This method must not panic because guest-memory validation depends on it.
    #[no_panic]
    fn guest_size() -> u32;

    /// Returns the required alignment of this type, in bytes, for both guest
    /// and host memory.
    ///
    /// This method must not panic because guest-memory validation depends on it.
    #[no_panic]
    fn guest_align() -> usize;

    /// Reads this value from the provided `ptr`.
    ///
    /// Must internally perform any safety checks necessary and is allowed to
    /// fail if the bytes pointed to are also invalid.
    ///
    /// Typically if you're implementing this by hand you'll want to delegate to
    /// other safe implementations of this trait (e.g. for primitive types like
    /// `u32`) rather than writing lots of raw code yourself.
    fn read(mem: &GuestMemory, ptr: GuestPtr<Self>) -> Result<Self, GuestError>;

    /// Writes a value to `ptr` after verifying that `ptr` is indeed valid to
    /// store `val`.
    ///
    /// Similar to `read`, you'll probably want to implement this in terms of
    /// other primitives.
    fn write(mem: &mut GuestMemory, ptr: GuestPtr<Self>, val: Self) -> Result<(), GuestError>;
}

/// A trait for `GuestType`s that have the same representation in guest memory
/// as in Rust. These types can be used with the `GuestPtr::as_slice` method to
/// view as a slice.
///
/// Unsafe trait because a correct `GuestTypeTransparent` implementation ensures
/// that the `GuestPtr::as_slice` methods are safe, notably that the
/// representation on the host matches the guest and all bit patterns are
/// valid. Wiggle implements this for primitive types with matching
/// representations. Generated records and variants use field-by-field
/// conversions instead and should not implement this trait.
///
/// # Safety
///
/// Implementors must guarantee that every possible guest byte representation
/// is a valid `Self`, and that the guest layout reported by `GuestType` is
/// compatible with the host layout for bytewise access.
pub unsafe trait GuestTypeTransparent: GuestType {}

#[no_panic]
fn atomic_ref<A>(
    bytes: &[UnsafeCell<u8>],
    guest_size: u32,
    region: Region,
) -> Result<&A, GuestError> {
    let atomic_size = mem::size_of::<A>();
    let guest_size = match usize::try_from(guest_size) {
        Ok(size) => size,
        Err(error) => return Err(GuestError::TryFromIntError(error)),
    };
    if guest_size != atomic_size || bytes.len() != atomic_size {
        return Err(GuestError::SliceLengthsDiffer);
    }

    let atomic_align = mem::align_of::<A>();
    if atomic_align == 0 {
        return Err(GuestError::SliceLengthsDiffer);
    }
    let cell = match bytes.first() {
        Some(cell) => cell,
        None => return Err(GuestError::SliceLengthsDiffer),
    };
    let cell_ptr = cell as *const UnsafeCell<u8>;
    if (cell_ptr as usize) % atomic_align != 0 {
        return Err(GuestError::PtrNotAligned(region, atomic_align as u32));
    }

    // SAFETY: the slice has exactly the atomic's size, and the first byte cell
    // has the atomic's required alignment. Callers use this only for integer
    // atomic types, for which every bit pattern is valid.
    Ok(unsafe { &*cell.get().cast::<A>() })
}

macro_rules! integer_primitives {
    ($([$ty:ident, $ty_atomic:ident],)*) => ($(
        impl GuestType for $ty {
            #[inline]
            #[no_panic]
            fn guest_size() -> u32 { mem::size_of::<Self>() as u32 }
            #[inline]
            #[no_panic]
            fn guest_align() -> usize { mem::align_of::<Self>() }

            #[inline]
            #[no_panic]
            fn read(mem: &GuestMemory, ptr: GuestPtr<Self>) -> Result<Self, GuestError> {
                // Validate the guest range and the byte pointer's alignment
                // before casting it to an atomic pointer.
                let offset = ptr.offset();
                let byte_len = usize::try_from(Self::guest_size())?;
                let host_ptr = mem.validate_size_align::<Self>(offset, 1, byte_len)?;
                let region = Region::new(offset, Self::guest_size());
                let host_ptr = atomic_ref::<$ty_atomic>(&host_ptr, Self::guest_size(), region)?;

                // If the accessed memory is shared, we need to load the bytes
                // with the correct memory consistency. We could check if the
                // memory is shared each time, but we expect little performance
                // difference between an additional branch and a relaxed memory
                // access and thus always do the relaxed access here.
                let val = host_ptr.load(Ordering::Relaxed);

                // And as a final operation convert from the little-endian wasm
                // value to a native-endian value for the host.
                Ok($ty::from_le(val))
            }

            #[inline]
            #[no_panic]
            fn write(mem: &mut GuestMemory, ptr: GuestPtr<Self>, val: Self) -> Result<(), GuestError> {
                // See `read` above for various checks here.
                let val = val.to_le();
                let offset = ptr.offset();
                let byte_len = usize::try_from(Self::guest_size())?;
                let host_ptr = mem.validate_size_align_mut::<Self>(offset, 1, byte_len)?;
                let region = Region::new(offset, Self::guest_size());
                let atomic_value_ref =
                    atomic_ref::<$ty_atomic>(&host_ptr, Self::guest_size(), region)?;
                atomic_value_ref.store(val, Ordering::Relaxed);
                Ok(())
            }
        }

        unsafe impl GuestTypeTransparent for $ty {}

    )*)
}

macro_rules! float_primitives {
    ($([$ty:ident, $ty_unsigned:ident, $ty_atomic:ident],)*) => ($(
        impl GuestType for $ty {
            #[inline]
            #[no_panic]
            fn guest_size() -> u32 { mem::size_of::<Self>() as u32 }
            #[inline]
            #[no_panic]
            fn guest_align() -> usize { mem::align_of::<Self>() }

            #[inline]
            #[no_panic]
            fn read(mem: &GuestMemory, ptr: GuestPtr<Self>) -> Result<Self, GuestError> {
                match <$ty_unsigned as GuestType>::read(mem, ptr.cast()) {
                    Ok(bits) => Ok($ty::from_bits(bits)),
                    Err(error) => Err(error),
                }
            }

            #[inline]
            #[no_panic]
            fn write(mem:&mut GuestMemory, ptr: GuestPtr<Self>, val: Self) -> Result<(), GuestError> {
                <$ty_unsigned as GuestType>::write(mem, ptr.cast(), val.to_bits())
            }
        }

        unsafe impl GuestTypeTransparent for $ty {}

    )*)
}

integer_primitives! {
    // signed
    [i8, AtomicI8], [i16, AtomicI16], [i32, AtomicI32], [i64, AtomicI64],
    // unsigned
    [u8, AtomicU8], [u16, AtomicU16], [u32, AtomicU32], [u64, AtomicU64],
}

float_primitives! {
    [f32, u32, AtomicU32], [f64, u64, AtomicU64],
}

#[cfg(test)]
mod tests {
    use super::*;

    #[repr(align(16))]
    struct AlignedBytes([UnsafeCell<u8>; 8]);

    #[test]
    fn atomic_ref_rejects_mismatched_byte_extent() {
        let bytes = AlignedBytes(std::array::from_fn(|_| UnsafeCell::new(0)));

        assert!(matches!(
            atomic_ref::<AtomicU32>(&bytes.0[..4], 3, Region::new(0, 3)),
            Err(GuestError::SliceLengthsDiffer)
        ));
    }

    #[test]
    fn atomic_ref_rejects_misaligned_bytes() {
        let bytes = AlignedBytes(std::array::from_fn(|_| UnsafeCell::new(0)));

        assert!(matches!(
            atomic_ref::<AtomicU32>(&bytes.0[1..5], 4, Region::new(1, 4)),
            Err(GuestError::PtrNotAligned(
                Region { start: 1, len: 4 },
                alignment
            )) if alignment as usize == mem::align_of::<AtomicU32>()
        ));
    }
}

// Support pointers-to-pointers where pointers are always 32-bits in wasm land
impl<T> GuestType for GuestPtr<T> {
    #[inline]
    #[no_panic]
    fn guest_size() -> u32 {
        u32::guest_size()
    }

    #[inline]
    #[no_panic]
    fn guest_align() -> usize {
        u32::guest_align()
    }

    fn read(mem: &GuestMemory, ptr: GuestPtr<Self>) -> Result<Self, GuestError> {
        let offset = u32::read(mem, ptr.cast())?;
        Ok(GuestPtr::new(offset))
    }

    fn write(mem: &mut GuestMemory, ptr: GuestPtr<Self>, val: Self) -> Result<(), GuestError> {
        u32::write(mem, ptr.cast(), val.offset())
    }
}

// Support pointers-to-arrays where pointers are always 32-bits in wasm land
impl<T> GuestType for GuestPtr<[T]>
where
    T: GuestType,
{
    #[inline]
    #[no_panic]
    fn guest_size() -> u32 {
        u32::guest_size() * 2
    }

    #[inline]
    #[no_panic]
    fn guest_align() -> usize {
        u32::guest_align()
    }

    fn read(mem: &GuestMemory, ptr: GuestPtr<Self>) -> Result<Self, GuestError> {
        let ptr = ptr.cast::<u32>();
        let offset = u32::read(mem, ptr)?;
        let len = u32::read(mem, ptr.add(1)?)?;
        Ok(GuestPtr::new(offset).as_array(len))
    }

    fn write(mem: &mut GuestMemory, ptr: GuestPtr<Self>, val: Self) -> Result<(), GuestError> {
        let (offset, len) = val.offset();
        let ptr = ptr.cast::<u32>();
        u32::write(mem, ptr, offset)?;
        u32::write(mem, ptr.add(1)?, len)?;
        Ok(())
    }
}
