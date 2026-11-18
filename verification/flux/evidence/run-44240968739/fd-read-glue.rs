        pub async fn fd_read(ctx: &mut (impl WasiSnapshotPreview1),
            memory: &mut wiggle::GuestMemory<'_>, arg0: i32, arg1: i32,
            arg2: i32, arg3: i32) -> wiggle::error::Result<i32> {
            use std::convert::TryFrom as _;
            use wiggle::tracing::Instrument as _;
            let _span =
                {
                    use ::tracing::__macro_support::Callsite as _;
                    static __CALLSITE: ::tracing::callsite::DefaultCallsite =
                        {
                            static META: ::tracing::Metadata<'static> =
                                {
                                    ::tracing_core::metadata::Metadata::new("wiggle abi",
                                        "wasmtime_wasi::p1::wasi_snapshot_preview1",
                                        wiggle::tracing::Level::TRACE,
                                        ::tracing_core::__macro_support::Option::Some("crates/wasi/src/p1.rs"),
                                        ::tracing_core::__macro_support::Option::Some(857u32),
                                        ::tracing_core::__macro_support::Option::Some("wasmtime_wasi::p1::wasi_snapshot_preview1"),
                                        ::tracing_core::field::FieldSet::new(&["module",
                                                        "function"],
                                            ::tracing_core::callsite::Identifier(&__CALLSITE)),
                                        ::tracing::metadata::Kind::SPAN)
                                };
                            ::tracing::callsite::DefaultCallsite::new(&META)
                        };
                    let mut interest = ::tracing::subscriber::Interest::never();
                    if wiggle::tracing::Level::TRACE <=
                                        ::tracing::level_filters::STATIC_MAX_LEVEL &&
                                    wiggle::tracing::Level::TRACE <=
                                        ::tracing::level_filters::LevelFilter::current() &&
                                { interest = __CALLSITE.interest(); !interest.is_never() }
                            &&
                            ::tracing::__macro_support::__is_enabled(__CALLSITE.metadata(),
                                interest) {
                        let meta = __CALLSITE.metadata();
                        ::tracing::Span::new(meta,
                            &{
                                    #[allow(unused_imports)]
                                    use ::tracing::field::{debug, display, Value};
                                    let mut iter = meta.fields().iter();
                                    meta.fields().value_set(&[(&::tracing::__macro_support::Iterator::next(&mut iter).expect("FieldSet corrupted (this is a bug)"),
                                                        ::tracing::__macro_support::Option::Some(&"wasi_snapshot_preview1"
                                                                as &dyn Value)),
                                                    (&::tracing::__macro_support::Iterator::next(&mut iter).expect("FieldSet corrupted (this is a bug)"),
                                                        ::tracing::__macro_support::Option::Some(&"fd_read" as
                                                                &dyn Value))])
                                })
                    } else {
                        let span =
                            ::tracing::__macro_support::__disabled_span(__CALLSITE.metadata());
                        {};
                        span
                    }
                };
            async move
                        {
                        let fd = Fd::from(arg0);
                        let iovs =
                            wiggle::GuestPtr::<[Iovec]>::new((arg1 as u32,
                                    arg2 as u32));
                        ;
                        {
                            use ::tracing::__macro_support::Callsite as _;
                            static __CALLSITE: ::tracing::callsite::DefaultCallsite =
                                {
                                    static META: ::tracing::Metadata<'static> =
                                        {
                                            ::tracing_core::metadata::Metadata::new("event crates/wasi/src/p1.rs:857",
                                                "wasmtime_wasi::p1::wasi_snapshot_preview1",
                                                wiggle::tracing::Level::TRACE,
                                                ::tracing_core::__macro_support::Option::Some("crates/wasi/src/p1.rs"),
                                                ::tracing_core::__macro_support::Option::Some(857u32),
                                                ::tracing_core::__macro_support::Option::Some("wasmtime_wasi::p1::wasi_snapshot_preview1"),
                                                ::tracing_core::field::FieldSet::new(&["fd", "iovs"],
                                                    ::tracing_core::callsite::Identifier(&__CALLSITE)),
                                                ::tracing::metadata::Kind::EVENT)
                                        };
                                    ::tracing::callsite::DefaultCallsite::new(&META)
                                };
                            let enabled =
                                wiggle::tracing::Level::TRACE <=
                                            ::tracing::level_filters::STATIC_MAX_LEVEL &&
                                        wiggle::tracing::Level::TRACE <=
                                            ::tracing::level_filters::LevelFilter::current() &&
                                    {
                                        let interest = __CALLSITE.interest();
                                        !interest.is_never() &&
                                            ::tracing::__macro_support::__is_enabled(__CALLSITE.metadata(),
                                                interest)
                                    };
                            if enabled {
                                (|value_set: ::tracing::field::ValueSet|
                                            {
                                                let meta = __CALLSITE.metadata();
                                                ::tracing::Event::dispatch(meta, &value_set);
                                                ;
                                            })({
                                        #[allow(unused_imports)]
                                        use ::tracing::field::{debug, display, Value};
                                        let mut iter = __CALLSITE.metadata().fields().iter();
                                        __CALLSITE.metadata().fields().value_set(&[(&::tracing::__macro_support::Iterator::next(&mut iter).expect("FieldSet corrupted (this is a bug)"),
                                                            ::tracing::__macro_support::Option::Some(&wiggle::tracing::field::display(&fd)
                                                                    as &dyn Value)),
                                                        (&::tracing::__macro_support::Iterator::next(&mut iter).expect("FieldSet corrupted (this is a bug)"),
                                                            ::tracing::__macro_support::Option::Some(&wiggle::tracing::field::debug(&iovs)
                                                                    as &dyn Value))])
                                    });
                            } else { ; }
                        };
                        let ret =
                            WasiSnapshotPreview1::fd_read(ctx, memory, fd, iovs).await;
                        {
                            use ::tracing::__macro_support::Callsite as _;
                            static __CALLSITE: ::tracing::callsite::DefaultCallsite =
                                {
                                    static META: ::tracing::Metadata<'static> =
                                        {
                                            ::tracing_core::metadata::Metadata::new("event crates/wasi/src/p1.rs:857",
                                                "wasmtime_wasi::p1::wasi_snapshot_preview1",
                                                wiggle::tracing::Level::TRACE,
                                                ::tracing_core::__macro_support::Option::Some("crates/wasi/src/p1.rs"),
                                                ::tracing_core::__macro_support::Option::Some(857u32),
                                                ::tracing_core::__macro_support::Option::Some("wasmtime_wasi::p1::wasi_snapshot_preview1"),
                                                ::tracing_core::field::FieldSet::new(&["result"],
                                                    ::tracing_core::callsite::Identifier(&__CALLSITE)),
                                                ::tracing::metadata::Kind::EVENT)
                                        };
                                    ::tracing::callsite::DefaultCallsite::new(&META)
                                };
                            let enabled =
                                wiggle::tracing::Level::TRACE <=
                                            ::tracing::level_filters::STATIC_MAX_LEVEL &&
                                        wiggle::tracing::Level::TRACE <=
                                            ::tracing::level_filters::LevelFilter::current() &&
                                    {
                                        let interest = __CALLSITE.interest();
                                        !interest.is_never() &&
                                            ::tracing::__macro_support::__is_enabled(__CALLSITE.metadata(),
                                                interest)
                                    };
                            if enabled {
                                (|value_set: ::tracing::field::ValueSet|
                                            {
                                                let meta = __CALLSITE.metadata();
                                                ::tracing::Event::dispatch(meta, &value_set);
                                                ;
                                            })({
                                        #[allow(unused_imports)]
                                        use ::tracing::field::{debug, display, Value};
                                        let mut iter = __CALLSITE.metadata().fields().iter();
                                        __CALLSITE.metadata().fields().value_set(&[(&::tracing::__macro_support::Iterator::next(&mut iter).expect("FieldSet corrupted (this is a bug)"),
                                                            ::tracing::__macro_support::Option::Some(&wiggle::tracing::field::debug(&ret)
                                                                    as &dyn Value))])
                                    });
                            } else { ; }
                        };
                        return Ok(match ret {
                                    Ok(e) => {
                                        memory.write(wiggle::GuestPtr::<Size>::new(arg3 as u32),
                                                    e).map_err(|e|
                                                    {
                                                        wiggle::GuestError::InFunc {
                                                            modulename: "wasi_snapshot_preview1",
                                                            funcname: "fd_read",
                                                            location: "write size",
                                                            err: Box::new(wiggle::GuestError::from(e)),
                                                        }
                                                    })?;
                                        ;
                                        <Errno as wiggle::GuestErrorType>::success() as i32
                                    }
                                    Err(e) => { e.downcast()? as i32 }
                                })
                    }.instrument(_span).await
        }
