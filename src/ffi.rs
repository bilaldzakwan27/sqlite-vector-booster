//! SQLite extension ABI prefix through SQLite 3.7.3's create_function_v2.
//!
//! Unused slots retain C function-pointer representation. Field order is defined by
//! <https://sqlite.org/src/file/src/sqlite3ext.h>; SQLite only appends new slots.

use std::ffi::{c_char, c_int, c_void};

#[repr(C)]
pub struct Database {
    _private: [u8; 0],
}

#[repr(C)]
pub struct Context {
    _private: [u8; 0],
}

#[repr(C)]
pub struct Value {
    _private: [u8; 0],
}

pub type Scalar = unsafe extern "C" fn(*mut Context, c_int, *mut *mut Value);
pub type CreateFunction = unsafe extern "C" fn(
    *mut Database,
    *const c_char,
    c_int,
    c_int,
    *mut c_void,
    Option<Scalar>,
    Option<Scalar>,
    Option<unsafe extern "C" fn(*mut Context)>,
    Option<unsafe extern "C" fn(*mut c_void)>,
) -> c_int;

type Unused = Option<unsafe extern "C" fn()>;

#[repr(C)]
pub struct ApiRoutines {
    _aggregate_context: Unused,
    _aggregate_count: Unused,
    _bind_blob: Unused,
    _bind_double: Unused,
    _bind_int: Unused,
    _bind_int64: Unused,
    _bind_null: Unused,
    _bind_parameter_count: Unused,
    _bind_parameter_index: Unused,
    _bind_parameter_name: Unused,
    _bind_text: Unused,
    _bind_text16: Unused,
    _bind_value: Unused,
    _busy_handler: Unused,
    _busy_timeout: Unused,
    _changes: Unused,
    _close: Unused,
    _collation_needed: Unused,
    _collation_needed16: Unused,
    _column_blob: Unused,
    _column_bytes: Unused,
    _column_bytes16: Unused,
    _column_count: Unused,
    _column_database_name: Unused,
    _column_database_name16: Unused,
    _column_decltype: Unused,
    _column_decltype16: Unused,
    _column_double: Unused,
    _column_int: Unused,
    _column_int64: Unused,
    _column_name: Unused,
    _column_name16: Unused,
    _column_origin_name: Unused,
    _column_origin_name16: Unused,
    _column_table_name: Unused,
    _column_table_name16: Unused,
    _column_text: Unused,
    _column_text16: Unused,
    _column_type: Unused,
    _column_value: Unused,
    _commit_hook: Unused,
    _complete: Unused,
    _complete16: Unused,
    _create_collation: Unused,
    _create_collation16: Unused,
    _create_function: Unused,
    _create_function16: Unused,
    _create_module: Unused,
    _data_count: Unused,
    _db_handle: Unused,
    _declare_vtab: Unused,
    _enable_shared_cache: Unused,
    _errcode: Unused,
    _errmsg: Unused,
    _errmsg16: Unused,
    _exec: Unused,
    _expired: Unused,
    _finalize: Unused,
    _free: Unused,
    _free_table: Unused,
    _get_autocommit: Unused,
    _get_auxdata: Unused,
    _get_table: Unused,
    _global_recover: Unused,
    _interruptx: Unused,
    _last_insert_rowid: Unused,
    _libversion: Unused,
    pub libversion_number: Option<unsafe extern "C" fn() -> c_int>,
    pub malloc: Option<unsafe extern "C" fn(c_int) -> *mut c_void>,
    _mprintf: Unused,
    _open: Unused,
    _open16: Unused,
    _prepare: Unused,
    _prepare16: Unused,
    _profile: Unused,
    _progress_handler: Unused,
    _realloc: Unused,
    _reset: Unused,
    _result_blob: Unused,
    pub result_double: Option<unsafe extern "C" fn(*mut Context, f64)>,
    pub result_error: Option<unsafe extern "C" fn(*mut Context, *const c_char, c_int)>,
    _result_error16: Unused,
    _result_int: Unused,
    _result_int64: Unused,
    pub result_null: Option<unsafe extern "C" fn(*mut Context)>,
    _result_text: Unused,
    _result_text16: Unused,
    _result_text16be: Unused,
    _result_text16le: Unused,
    _result_value: Unused,
    _rollback_hook: Unused,
    _set_authorizer: Unused,
    _set_auxdata: Unused,
    _xsnprintf: Unused,
    _step: Unused,
    _table_column_metadata: Unused,
    _thread_cleanup: Unused,
    _total_changes: Unused,
    _trace: Unused,
    _transfer_bindings: Unused,
    _update_hook: Unused,
    _user_data: Unused,
    pub value_blob: Option<unsafe extern "C" fn(*mut Value) -> *const c_void>,
    pub value_bytes: Option<unsafe extern "C" fn(*mut Value) -> c_int>,
    _value_bytes16: Unused,
    _value_double: Unused,
    _value_int: Unused,
    _value_int64: Unused,
    _value_numeric_type: Unused,
    _value_text: Unused,
    _value_text16: Unused,
    _value_text16be: Unused,
    _value_text16le: Unused,
    pub value_type: Option<unsafe extern "C" fn(*mut Value) -> c_int>,
    _vmprintf: Unused,
    _overload_function: Unused,
    _prepare_v2: Unused,
    _prepare16_v2: Unused,
    _clear_bindings: Unused,
    _create_module_v2: Unused,
    _bind_zeroblob: Unused,
    _blob_bytes: Unused,
    _blob_close: Unused,
    _blob_open: Unused,
    _blob_read: Unused,
    _blob_write: Unused,
    _create_collation_v2: Unused,
    _file_control: Unused,
    _memory_highwater: Unused,
    _memory_used: Unused,
    _mutex_alloc: Unused,
    _mutex_enter: Unused,
    _mutex_free: Unused,
    _mutex_leave: Unused,
    _mutex_try: Unused,
    _open_v2: Unused,
    _release_memory: Unused,
    pub result_error_nomem: Option<unsafe extern "C" fn(*mut Context)>,
    _result_error_toobig: Unused,
    _sleep: Unused,
    _soft_heap_limit: Unused,
    _vfs_find: Unused,
    _vfs_register: Unused,
    _vfs_unregister: Unused,
    _xthreadsafe: Unused,
    _result_zeroblob: Unused,
    _result_error_code: Unused,
    _test_control: Unused,
    _randomness: Unused,
    _context_db_handle: Unused,
    _extended_result_codes: Unused,
    _limit: Unused,
    _next_stmt: Unused,
    _sql: Unused,
    _status: Unused,
    _backup_finish: Unused,
    _backup_init: Unused,
    _backup_pagecount: Unused,
    _backup_remaining: Unused,
    _backup_step: Unused,
    _compileoption_get: Unused,
    _compileoption_used: Unused,
    pub create_function_v2: Option<CreateFunction>,
}

pub const OK: c_int = 0;
pub const ERROR: c_int = 1;
pub const MISUSE: c_int = 21;
pub const BLOB: c_int = 4;
pub const NULL: c_int = 5;
pub const UTF8: c_int = 1;
pub const DETERMINISTIC: c_int = 0x800;
pub const INNOCUOUS: c_int = 0x200000;

#[cfg(test)]
mod tests {
    use super::*;
    use std::mem::{offset_of, size_of};

    #[test]
    fn extension_abi_offsets() {
        let slot = size_of::<Unused>();
        assert_eq!(size_of::<ApiRoutines>(), 163 * slot);
        assert_eq!(offset_of!(ApiRoutines, libversion_number), 67 * slot);
        assert_eq!(offset_of!(ApiRoutines, malloc), 68 * slot);
        assert_eq!(offset_of!(ApiRoutines, result_double), 79 * slot);
        assert_eq!(offset_of!(ApiRoutines, result_error), 80 * slot);
        assert_eq!(offset_of!(ApiRoutines, result_null), 84 * slot);
        assert_eq!(offset_of!(ApiRoutines, value_blob), 102 * slot);
        assert_eq!(offset_of!(ApiRoutines, value_bytes), 103 * slot);
        assert_eq!(offset_of!(ApiRoutines, value_type), 113 * slot);
        assert_eq!(offset_of!(ApiRoutines, result_error_nomem), 137 * slot);
        assert_eq!(offset_of!(ApiRoutines, create_function_v2), 162 * slot);
    }
}
