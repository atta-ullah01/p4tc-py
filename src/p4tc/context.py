"""Runtime context — netlink transport for CRUD operations."""

from __future__ import annotations

from ._ffi import ffi, _require_lib
from ._schema import _get_schema
from .errors import (
    ContextError, CRUDError, EntryError, KeyError_, ObjectError,
    _capture_errno,
)
from .types import Entity, MsgFlags, ObjType, Phase, Transport


class Context:
    """Netlink transport handle for table CRUD.

    Thread-safe (the C library serialises access internally).
    Intended to be used as a context manager::

        with p4tc.Context() as ctx:
            ctx.insert(...)
    """

    def __init__(self, transport=Transport.NETLINK, *, _lib=None):
        self._lib = _lib or _require_lib()
        self._ctx = self._lib.p4tc_runt_ctx_create(int(transport))
        if self._ctx == ffi.NULL:
            raise ContextError("failed to create context",
                               errno=_capture_errno())

        self._responses = []
        self._user_cb = None
        self._aborted = False

        # Build a cffi callback and store it as an instance attribute so it
        # is kept alive (preventing garbage collection) for as long as the
        # context exists.
        self._c_callback = ffi.callback(
            "int(const struct p4tc_obj*, struct p4tc_runt_ctx*,"
            " uint64_t*, int)",
            self._on_response,
        )
        self._lib.p4tc_runt_ctx_dflt_cb_set(self._ctx, self._c_callback)



    def _on_response(self, obj_ptr, ctx_ptr, cookie_ptr, phase_val):
        """Invoked by the C library for every response message.

        The library calls this during ``p4tc_resp_handle`` or
        ``p4tc_dump_handle``.  We record the raw ``p4tc_obj`` pointers
        and forward to the user callback if one is set.

        NOTE: the C API currently lacks getter functions, so we cannot
        extract key/param data from *obj_ptr* yet.  Once upstream adds
        accessors we will parse them here and return structured objects.
        """
        try:
            phase = Phase(phase_val)

            if phase in (Phase.SOT, Phase.MOT):
                if obj_ptr != ffi.NULL:
                    self._responses.append(obj_ptr)
                    if self._user_cb is not None:
                        self._user_cb(obj_ptr, phase)

            elif phase == Phase.EOT:
                pass  # transaction complete, nothing to do

            elif phase == Phase.ABT:
                self._aborted = True
                return -1

            return 0
        except Exception:
            # Exceptions cannot propagate through C; cffi will print
            # the traceback to stderr.  Return -1 so the C side aborts.
            return -1

    def _reset_response_state(self):
        """Clear per-operation bookkeeping before a new CRUD call."""
        self._responses.clear()
        self._aborted = False

    def _recv_response(self, flags, pipeline, table, op_name):
        """Block on a kernel response when ACK or ECHO was requested."""
        if int(flags) & int(MsgFlags.ACK | MsgFlags.ECHO):
            ret = self._lib.p4tc_resp_handle(self._ctx)
            if ret != 0 or self._aborted:
                raise CRUDError(
                    f"{op_name} response error on '{pipeline}/{table}'",
                    errno=_capture_errno(),
                )



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



    def _build_and_send(self, crud_fn, pipeline, table, *,
                        key=None, action=None, filter_str=None,
                        flags=0, priority=0, entity=Entity.TC,
                        aging_ms=None, profile_id=None,
                        permissions=None, dynamic=None):
        """Build a ``p4tc_obj``, attach key/action, and fire the CRUD call."""
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

                tbl_key = ffi.gc(raw_key, lib.p4tc_key_destroy)

                entry = lib.p4tc_alloc_tbl_entry(obj, raw_key,
                                                 0, int(entity))
                if entry == ffi.NULL:
                    raise EntryError(f"alloc_tbl_entry failed for '{table}'",
                                     errno=_capture_errno())
                self._apply_entry_attrs(lib, entry, priority=priority,
                                        aging_ms=aging_ms,
                                        profile_id=profile_id,
                                        permissions=permissions,
                                        dynamic=dynamic)
                # key ownership transferred to obj
                ffi.release(tbl_key)

                if action is not None:
                    self._attach_action(lib, entry, action, table_schema)

            elif action is not None:
                entry = lib.p4tc_alloc_tbl_entry(obj, ffi.NULL,
                                                 0, int(entity))
                if entry == ffi.NULL:
                    raise EntryError(f"alloc_tbl_entry failed for '{table}'",
                                     errno=_capture_errno())
                self._apply_entry_attrs(lib, entry, priority=priority,
                                        aging_ms=aging_ms,
                                        profile_id=profile_id,
                                        permissions=permissions,
                                        dynamic=dynamic)
                self._attach_action(lib, entry, action, table_schema)

            ret = crud_fn(self._ctx, obj, int(flags), ffi.NULL, ffi.NULL)
            if ret != 0:
                raise CRUDError(f"CRUD failed on '{pipeline}/{table}'",
                                errno=_capture_errno())
            return ret
        finally:
            lib.p4tc_obj_destroy(obj)

    @staticmethod
    def _apply_entry_attrs(lib, entry, *, priority=0, aging_ms=None,
                           profile_id=None, permissions=None,
                           dynamic=None):
        """Call C setter functions for optional table entry attributes.

        Only calls setters for values that were explicitly provided
        (i.e. not None / not zero for priority).
        """
        if priority > 0:
            lib.p4tc_runt_tbl_attrs_prio_set(entry, priority)
        if aging_ms is not None:
            lib.p4tc_runt_tbl_attrs_aging_set(entry, aging_ms)
        if profile_id is not None:
            lib.p4tc_runt_tbl_attrs_profile_id_set(entry, profile_id)
        if permissions is not None:
            lib.p4tc_runt_tbl_attrs_perms_set(entry, permissions)
        if dynamic is not None:
            lib.p4tc_runt_tbl_attrs_dyn_set(entry, 1 if dynamic else 0)

    @staticmethod
    def _attach_action(lib, entry, action, table_schema=None):
        """Attach an action with its parameters to a table entry."""
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



    def insert(self, pipeline, table, *, key, action,
               priority=0, entity=Entity.TC, flags=0,
               aging_ms=None, profile_id=None,
               permissions=None, dynamic=None):
        """Create a new table entry.

        Optional entry attributes:
            aging_ms:    entry aging timeout in milliseconds
            profile_id:  profile identifier
            permissions: permission bits (CRUDS+XP)
            dynamic:     mark entry as dynamic (bool)
        """
        self._reset_response_state()
        self._build_and_send(self._lib.p4tc_create, pipeline, table,
                             key=key, action=action, priority=priority,
                             entity=entity, flags=int(flags),
                             aging_ms=aging_ms, profile_id=profile_id,
                             permissions=permissions, dynamic=dynamic)
        self._recv_response(flags, pipeline, table, "insert")

    def update(self, pipeline, table, *, key=None, action=None,
               filter_str=None, priority=0, entity=Entity.TC, flags=0,
               aging_ms=None, profile_id=None,
               permissions=None, dynamic=None):
        """Update an existing table entry.

        Optional entry attributes:
            aging_ms:    entry aging timeout in milliseconds
            profile_id:  profile identifier
            permissions: permission bits (CRUDS+XP)
            dynamic:     mark entry as dynamic (bool)
        """
        self._reset_response_state()
        self._build_and_send(self._lib.p4tc_update, pipeline, table,
                             key=key, action=action, filter_str=filter_str,
                             priority=priority, entity=entity, flags=int(flags),
                             aging_ms=aging_ms, profile_id=profile_id,
                             permissions=permissions, dynamic=dynamic)
        self._recv_response(flags, pipeline, table, "update")

    def get(self, pipeline, table, *, key=None,
            filter_str=None, flags=MsgFlags.ECHO, callback=None):
        """Read table entries.

        *key* given → single entry.  *key* omitted → all entries.
        *callback(obj_ptr, phase)* is called for each response object.
        Returns ``None`` until upstream adds getter functions.
        """
        self._reset_response_state()
        self._user_cb = callback
        try:
            self._build_and_send(self._lib.p4tc_get, pipeline, table,
                                 key=key, filter_str=filter_str,
                                 flags=int(flags))
            self._recv_response(flags, pipeline, table, "get")
        finally:
            self._user_cb = None
        # TODO: parse and return Entry objects once C getters land
        return None

    def dump(self, pipeline, table, *, filter_str=None, callback=None):
        """Dump all entries from a table.

        Uses ``p4tc_dump_handle`` to iterate multi-part responses.
        *callback(obj_ptr, phase)* is called for each entry.
        Returns the number of response objects received.
        """
        self._reset_response_state()
        self._user_cb = callback
        try:
            lib = self._lib
            obj = lib.p4tc_obj_create(pipeline.encode(), int(ObjType.TABLE))
            if obj == ffi.NULL:
                raise ObjectError(f"obj_create failed for '{pipeline}'",
                                  errno=_capture_errno())
            try:
                lib.p4tc_obj_objname_set(obj, table.encode())
                if filter_str is not None:
                    lib.p4tc_obj_filter_set(obj, filter_str.encode())

                ret = lib.p4tc_get(self._ctx, obj,
                                   int(MsgFlags.ROOT), ffi.NULL, ffi.NULL)
                if ret != 0:
                    raise CRUDError(
                        f"dump send failed on '{pipeline}/{table}'",
                        errno=_capture_errno())
            finally:
                lib.p4tc_obj_destroy(obj)

            ret = lib.p4tc_dump_handle(self._ctx, self._c_callback)
            if ret != 0 or self._aborted:
                raise CRUDError(f"dump failed on '{pipeline}/{table}'",
                                errno=_capture_errno())
        finally:
            self._user_cb = None

        return len(self._responses)

    def delete(self, pipeline, table, *, key=None,
               filter_str=None, flags=0):
        """Delete entry/entries from a table."""
        self._reset_response_state()
        self._build_and_send(self._lib.p4tc_del, pipeline, table,
                             key=key, filter_str=filter_str, flags=int(flags))
        self._recv_response(flags, pipeline, table, "delete")

    def flush(self, pipeline, table, *, flags=0):
        """Delete all entries from a table."""
        self.delete(pipeline, table, flags=flags)


    def _build_extern_obj(self, pipeline, kind, instance, key,
                          params=None):
        """Build a p4tc_obj for an extern operation.

        Returns (obj, ext_attrs) — caller must destroy obj when done.
        """
        lib = self._lib
        obj = lib.p4tc_obj_create(pipeline.encode(), int(ObjType.EXTERN))
        if obj == ffi.NULL:
            raise ObjectError(f"obj_create failed for '{pipeline}'",
                              errno=_capture_errno())

        param_values = list(params.values()) if isinstance(params, dict) \
            else list(params or [])

        param_ptrs = [ffi.new("char[]", p.encode()) for p in param_values]
        param_arr = ffi.new("const char *[]", param_ptrs) \
            if param_ptrs else ffi.NULL

        ext = lib.p4tc_create_runt_ext(
            obj, kind.encode(), instance.encode(),
            key, len(param_values), param_arr,
        )
        if ext == ffi.NULL:
            lib.p4tc_obj_destroy(obj)
            raise EntryError(
                f"create_runt_ext failed for '{kind}/{instance}'",
                errno=_capture_errno())

        return obj

    def extern_insert(self, pipeline, kind, instance, *, key,
                      params=None, flags=0):
        """Create an extern instance entry."""
        self._reset_response_state()
        obj = self._build_extern_obj(pipeline, kind, instance, key, params)
        try:
            ret = self._lib.p4tc_create(self._ctx, obj, int(flags),
                                        ffi.NULL, ffi.NULL)
            if ret != 0:
                raise CRUDError(
                    f"extern create failed for '{kind}/{instance}'",
                    errno=_capture_errno())
        finally:
            self._lib.p4tc_obj_destroy(obj)
        self._recv_response(flags, pipeline, f"{kind}/{instance}",
                            "extern_insert")

    def extern_update(self, pipeline, kind, instance, *, key,
                      params=None, flags=0):
        """Update an extern instance entry."""
        self._reset_response_state()
        obj = self._build_extern_obj(pipeline, kind, instance, key, params)
        try:
            ret = self._lib.p4tc_update(self._ctx, obj, int(flags),
                                        ffi.NULL, ffi.NULL)
            if ret != 0:
                raise CRUDError(
                    f"extern update failed for '{kind}/{instance}'",
                    errno=_capture_errno())
        finally:
            self._lib.p4tc_obj_destroy(obj)
        self._recv_response(flags, pipeline, f"{kind}/{instance}",
                            "extern_update")

    def extern_get(self, pipeline, kind, instance, *, key,
                   flags=MsgFlags.ECHO, callback=None):
        """Read an extern instance entry.

        Returns None until C getter functions are available upstream.
        """
        self._reset_response_state()
        self._user_cb = callback
        try:
            obj = self._build_extern_obj(pipeline, kind, instance, key)
            try:
                ret = self._lib.p4tc_get(self._ctx, obj, int(flags),
                                         ffi.NULL, ffi.NULL)
                if ret != 0:
                    raise CRUDError(
                        f"extern get failed for '{kind}/{instance}'",
                        errno=_capture_errno())
            finally:
                self._lib.p4tc_obj_destroy(obj)
            self._recv_response(flags, pipeline, f"{kind}/{instance}",
                                "extern_get")
        finally:
            self._user_cb = None
        return None

    def extern_delete(self, pipeline, kind, instance, *, key, flags=0):
        """Delete an extern instance entry."""
        self._reset_response_state()
        obj = self._build_extern_obj(pipeline, kind, instance, key)
        try:
            ret = self._lib.p4tc_del(self._ctx, obj, int(flags),
                                     ffi.NULL, ffi.NULL)
            if ret != 0:
                raise CRUDError(
                    f"extern delete failed for '{kind}/{instance}'",
                    errno=_capture_errno())
        finally:
            self._lib.p4tc_obj_destroy(obj)
        self._recv_response(flags, pipeline, f"{kind}/{instance}",
                            "extern_delete")
