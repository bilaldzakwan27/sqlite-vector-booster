#![feature(portable_simd)]

mod ffi;
pub mod vector;

use ffi::{ApiRoutines, Context, Database, Scalar, Value};
use std::ffi::{c_char, c_int, c_void, CStr};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr;
use std::slice;
use std::sync::OnceLock;
use vector::{cosine_distance, l2_squared_distance, VectorError, MAX_DIMENSIONS};

struct Api {
    identity: usize,
    create_function: ffi::CreateFunction,
    result_double: unsafe extern "C" fn(*mut Context, f64),
    result_error: unsafe extern "C" fn(*mut Context, *const c_char, c_int),
    result_null: unsafe extern "C" fn(*mut Context),
    result_error_nomem: unsafe extern "C" fn(*mut Context),
    value_blob: unsafe extern "C" fn(*mut Value) -> *const c_void,
    value_bytes: unsafe extern "C" fn(*mut Value) -> c_int,
    value_type: unsafe extern "C" fn(*mut Value) -> c_int,
}

static API: OnceLock<Api> = OnceLock::new();
const COSINE_NAME: &CStr = c"vector_cosine_dist";
const L2_NAME: &CStr = c"vector_l2_dist";
const FLAGS: c_int = ffi::UTF8 | ffi::DETERMINISTIC | ffi::INNOCUOUS;

impl Api {
    unsafe fn read(raw: *const ApiRoutines) -> Option<Self> {
        let routines = unsafe { &*raw };
        Some(Self {
            identity: raw as usize,
            create_function: routines.create_function_v2?,
            result_double: routines.result_double?,
            result_error: routines.result_error?,
            result_null: routines.result_null?,
            result_error_nomem: routines.result_error_nomem?,
            value_blob: routines.value_blob?,
            value_bytes: routines.value_bytes?,
            value_type: routines.value_type?,
        })
    }

    unsafe fn register(&self, db: *mut Database, name: &CStr, callback: Option<Scalar>) -> c_int {
        unsafe {
            (self.create_function)(
                db,
                name.as_ptr(),
                2,
                FLAGS,
                ptr::null_mut(),
                callback,
                None,
                None,
                None,
            )
        }
    }

    unsafe fn error(&self, ctx: *mut Context, message: &str) {
        unsafe { (self.result_error)(ctx, message.as_ptr().cast(), message.len() as c_int) };
    }
}

unsafe fn init_error(raw: *const ApiRoutines, out: *mut *mut c_char, message: &CStr) {
    if out.is_null() {
        return;
    }
    let malloc = unsafe { ptr::addr_of!((*raw).malloc).read() };
    if let Some(malloc) = malloc {
        let bytes = message.to_bytes_with_nul();
        let target = unsafe { malloc(bytes.len() as c_int) }.cast::<c_char>();
        if !target.is_null() {
            unsafe {
                ptr::copy_nonoverlapping(bytes.as_ptr().cast(), target, bytes.len());
                *out = target;
            }
        }
    }
}

unsafe fn initialize(db: *mut Database, out: *mut *mut c_char, raw: *const ApiRoutines) -> c_int {
    let version = unsafe { ptr::addr_of!((*raw).libversion_number).read() };
    let Some(version) = version else {
        return ffi::MISUSE;
    };
    if unsafe { version() } < 3_031_000 {
        unsafe {
            init_error(
                raw,
                out,
                c"sqlite-vector-booster requires SQLite 3.31.0 or newer",
            )
        };
        return ffi::ERROR;
    }
    let Some(candidate) = (unsafe { Api::read(raw) }) else {
        unsafe { init_error(raw, out, c"required SQLite API functions are unavailable") };
        return ffi::ERROR;
    };
    let api = API.get_or_init(|| candidate);
    if api.identity != raw as usize {
        unsafe {
            init_error(
                raw,
                out,
                c"one extension instance cannot serve multiple SQLite engines",
            )
        };
        return ffi::ERROR;
    }
    let status = unsafe { api.register(db, COSINE_NAME, Some(cosine_callback)) };
    if status != ffi::OK {
        unsafe { init_error(raw, out, c"could not register vector_cosine_dist") };
        return status;
    }
    let status = unsafe { api.register(db, L2_NAME, Some(l2_callback)) };
    if status != ffi::OK {
        unsafe {
            api.register(db, COSINE_NAME, None);
            init_error(raw, out, c"could not register vector_l2_dist");
        }
    }
    status
}

/// Registers the extension's deterministic scalar functions with SQLite.
///
/// # Safety
/// `db` and `api` must be live handles supplied by SQLite's extension loader.
/// `error`, when non-null, must point to a writable SQLite error-message slot.
#[no_mangle]
pub unsafe extern "C" fn sqlite3_extension_init(
    db: *mut Database,
    error: *mut *mut c_char,
    api: *const ApiRoutines,
) -> c_int {
    if db.is_null() || api.is_null() {
        return ffi::MISUSE;
    }
    if !error.is_null() {
        unsafe { *error = ptr::null_mut() };
    }
    match catch_unwind(AssertUnwindSafe(|| unsafe { initialize(db, error, api) })) {
        Ok(status) => status,
        Err(_) => {
            unsafe {
                init_error(
                    api,
                    error,
                    c"panic while initializing sqlite-vector-booster",
                )
            };
            ffi::ERROR
        }
    }
}

#[derive(Clone, Copy)]
enum SqlError {
    Message(&'static str),
    Vector(VectorError),
    NoMemory,
}

impl From<VectorError> for SqlError {
    fn from(value: VectorError) -> Self {
        Self::Vector(value)
    }
}

unsafe fn blob<'a>(api: &Api, value: *mut Value) -> Result<&'a [u8], SqlError> {
    let length = unsafe { (api.value_bytes)(value) };
    if length <= 0 {
        return Err(VectorError::Empty.into());
    }
    if length % 4 != 0 {
        return Err(VectorError::InvalidLength.into());
    }
    if length as usize / 4 > MAX_DIMENSIONS {
        return Err(VectorError::TooManyDimensions.into());
    }
    let bytes = unsafe { (api.value_blob)(value) }.cast::<u8>();
    if bytes.is_null() {
        return Err(SqlError::NoMemory);
    }
    Ok(unsafe { slice::from_raw_parts(bytes, length as usize) })
}

unsafe fn evaluate(
    api: &Api,
    count: c_int,
    values: *mut *mut Value,
    cosine: bool,
) -> Result<Option<f64>, SqlError> {
    if count != 2 || values.is_null() {
        return Err(SqlError::Message(
            "exactly two vector arguments are required",
        ));
    }
    let args = unsafe { slice::from_raw_parts(values, 2) };
    if args[0].is_null() || args[1].is_null() {
        return Err(SqlError::Message("invalid SQLite value pointer"));
    }
    let a_type = unsafe { (api.value_type)(args[0]) };
    let b_type = unsafe { (api.value_type)(args[1]) };
    if a_type == ffi::NULL || b_type == ffi::NULL {
        return Ok(None);
    }
    if a_type != ffi::BLOB || b_type != ffi::BLOB {
        return Err(SqlError::Message("vector arguments must be BLOBs"));
    }
    let a = unsafe { blob(api, args[0]) }?;
    let b = unsafe { blob(api, args[1]) }?;
    let distance = if cosine {
        cosine_distance(a, b)?
    } else {
        l2_squared_distance(a, b)?
    };
    Ok(Some(distance))
}

unsafe fn invoke(ctx: *mut Context, count: c_int, values: *mut *mut Value, cosine: bool) {
    let Some(api) = API.get() else {
        return;
    };
    if ctx.is_null() {
        return;
    }
    let result = catch_unwind(AssertUnwindSafe(|| unsafe {
        evaluate(api, count, values, cosine)
    }));
    unsafe {
        match result {
            Ok(Ok(Some(value))) => (api.result_double)(ctx, value),
            Ok(Ok(None)) => (api.result_null)(ctx),
            Ok(Err(SqlError::NoMemory)) => (api.result_error_nomem)(ctx),
            Ok(Err(SqlError::Message(message))) => api.error(ctx, message),
            Ok(Err(SqlError::Vector(error))) => {
                let message = match error {
                    VectorError::Empty => "vectors must contain at least one f32",
                    VectorError::InvalidLength => "BLOB byte length must be a multiple of four",
                    VectorError::DimensionMismatch => "vector dimensions must match",
                    VectorError::TooManyDimensions => "vector dimension exceeds 1048576",
                    VectorError::NonFinite => "vector elements must be finite",
                    VectorError::ZeroNorm => "cosine distance is undefined for zero-norm vectors",
                };
                api.error(ctx, message);
            }
            Err(_) => api.error(ctx, "panic while evaluating vector distance"),
        }
    }
}

unsafe extern "C" fn cosine_callback(ctx: *mut Context, count: c_int, values: *mut *mut Value) {
    unsafe { invoke(ctx, count, values, true) };
}

unsafe extern "C" fn l2_callback(ctx: *mut Context, count: c_int, values: *mut *mut Value) {
    unsafe { invoke(ctx, count, values, false) };
}
