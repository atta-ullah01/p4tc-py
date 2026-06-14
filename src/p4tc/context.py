"""Runtime context — netlink transport for CRUD operations."""

from __future__ import annotations
from typing import Any

from ._ffi import ffi, _require_lib
from ._schema import _get_schema
from .errors import (
    ContextError, CRUDError, EntryError, KeyError_, ObjectError,
    _capture_errno,
)
from .types import Entity, ObjType, Transport


class Context:
    """Netlink transport handle for table CRUD.

    Thread-safe. Use as a context manager.
    """

    def __init__(self, transport=Transport.NETLINK, *, _lib=None):
        self._lib = _lib or _require_lib()
        self._ctx = self._lib.p4tc_runt_ctx_create(int(transport))
        if self._ctx == ffi.NULL:
            raise ContextError("failed to create context",
                               errno=_capture_errno())

    @property
    def is_valid(self):
        return self._ctx is not None and self._ctx != ffi.NULL

    def destroy(self):
        if self._ctx is not None and self._ctx != ffi.NULL:
            self._lib.p4tc_runt_ctx_destroy(self._ctx)
            self._ctx = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.destroy()

    def __del__(self):
        self.destroy()

    def __repr__(self):
        state = "valid" if self.is_valid else "destroyed"
        return f"Context({state})"

    # -- internal ---------------------------------------------------------

    def _build_and_send(self, crud_fn, pipeline, table, *,
                        key=None, action=None, filter_str=None,
                        flags=0, priority=0, entity=Entity.TC):
        """Build obj + key + action, then call the CRUD function."""
        lib = self._lib
        schema = _get_schema(pipeline)
        table_schema = schema.get_table(table) if schema else None

        obj = lib.p4tc_obj_create(pipeline.encode(), int(ObjType.TABLE))
        if obj == ffi.NULL:
            raise ObjectError(f"obj_create failed for '{pipeline}'",
                              errno=_capture_errno())

        try:
            lib.p4tc_obj_objname_set(obj, table.encode())

            if filter_str is not None:
                lib.p4tc_obj_filter_set(obj, filter_str.encode())

            if key is not None:
                # dict keys validated against schema for correct ordering
                if isinstance(key, dict):
                    if table_schema is not None:
                        key_values = table_schema.validate_key(key)
                    else:
                        key_values = list(key.values())
                else:
                    key_values = list(key)

                key_ptrs = [ffi.new("char[]", v.encode()) for v in key_values]
                key_arr = ffi.new("const char *[]", key_ptrs)
                raw_key = lib.p4tc_make_key(obj, len(key_values), key_arr)
                if raw_key == ffi.NULL:
                    raise KeyError_(f"make_key failed for {key}",
                                    errno=_capture_errno())

                # ffi.gc ensures cleanup if alloc_tbl_entry fails
                tbl_key = ffi.gc(raw_key, lib.p4tc_key_destroy)

                entry = lib.p4tc_alloc_tbl_entry(obj, raw_key,
                                                 priority, int(entity))
                if entry == ffi.NULL:
                    raise EntryError(f"alloc_tbl_entry failed for '{table}'",
                                     errno=_capture_errno())
                # key is now owned by obj
                ffi.release(tbl_key)

                if action is not None:
                    self._attach_action(lib, entry, action, table_schema)

            elif action is not None:
                entry = lib.p4tc_alloc_tbl_entry(obj, ffi.NULL,
                                                 priority, int(entity))
                if entry == ffi.NULL:
                    raise EntryError(f"alloc_tbl_entry failed for '{table}'",
                                     errno=_capture_errno())
                self._attach_action(lib, entry, action, table_schema)

            ret = crud_fn(self._ctx, obj, flags, ffi.NULL, ffi.NULL)
            if ret != 0:
                raise CRUDError(f"CRUD failed on '{pipeline}/{table}'",
                                errno=_capture_errno())
            return ret
        finally:
            lib.p4tc_obj_destroy(obj)

    @staticmethod
    def _attach_action(lib, entry, action, table_schema=None):
        """Attach an action to a table entry."""
        act_path, act_params = action
        if isinstance(act_params, dict):
            if table_schema:
                act_schema = table_schema.get_action(act_path)
                if act_schema:
                    param_values = act_schema.validate_params(act_params)
                else:
                    param_values = list(act_params.values())
            else:
                param_values = list(act_params.values())
        else:
            param_values = list(act_params)

        param_ptrs = [ffi.new("char[]", p.encode()) for p in param_values]
        param_arr = ffi.new("const char *[]", param_ptrs)
        act = lib.p4tc_create_runt_act(entry, act_path.encode(),
                                       len(param_values), param_arr)
        if act == ffi.NULL:
            raise EntryError(f"create_runt_act failed for '{act_path}'",
                             errno=_capture_errno())

    # -- public CRUD ------------------------------------------------------

    def insert(self, pipeline, table, *, key, action,
               priority=0, entity=Entity.TC, flags=0):
        """Create a new table entry."""
        self._build_and_send(self._lib.p4tc_create, pipeline, table,
                             key=key, action=action, priority=priority,
                             entity=entity, flags=flags)

    def update(self, pipeline, table, *, key=None, action=None,
               filter_str=None, priority=0, entity=Entity.TC, flags=0):
        """Update an existing table entry."""
        self._build_and_send(self._lib.p4tc_update, pipeline, table,
                             key=key, action=action, filter_str=filter_str,
                             priority=priority, entity=entity, flags=flags)

    def get(self, pipeline, table, *, key=None,
            filter_str=None, flags=0):
        """Read table entries. With key: single entry. Without: dump."""
        self._build_and_send(self._lib.p4tc_get, pipeline, table,
                             key=key, filter_str=filter_str, flags=flags)

    def delete(self, pipeline, table, *, key=None,
               filter_str=None, flags=0):
        """Delete entry/entries from a table."""
        self._build_and_send(self._lib.p4tc_del, pipeline, table,
                             key=key, filter_str=filter_str, flags=flags)

    def flush(self, pipeline, table, *, flags=0):
        """Delete all entries from a table."""
        self.delete(pipeline, table, flags=flags)
