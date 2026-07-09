"""Runtime context — netlink transport for CRUD operations."""

from __future__ import annotations

import threading

from ._ffi import ffi, _require_lib
from ._schema import _get_schema
from .entry import Action, ExternEntry, Param, TableEntry
from .errors import (
    ContextError, CRUDError, EntryError, KeyError_, ObjectError,
    SubscribeError, _capture_errno,
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
        self._subscriptions = []

        # The C library requires a default callback before any CRUD call.
        self._c_callback = ffi.callback(
            "int(const struct p4tc_obj*, struct p4tc_runt_ctx*,"
            " uint64_t*, int)",
            self._on_response,
        )
        self._lib.p4tc_runt_ctx_dflt_cb_set(self._ctx, self._c_callback)


    def _ensure_callback(self):
        """Register the default callback if not done yet."""
        if self._c_callback is not None:
            return
        self._c_callback = ffi.callback(
            "int(const struct p4tc_obj*, struct p4tc_runt_ctx*,"
            " uint64_t*, int)",
            self._on_response,
        )
        self._lib.p4tc_runt_ctx_dflt_cb_set(self._ctx, self._c_callback)


    def _on_response(self, obj_ptr, ctx_ptr, cookie_ptr, phase_val):
        """Default callback invoked by the C library per response.

        Records raw ``p4tc_obj`` pointers and forwards to the user
        callback.  Structured parsing is pending getter API integration.
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


    # response parsing

    @staticmethod
    def _parse_param(lib, p_ptr):
        name_ptr = lib.p4tc_runt_param_attrs_name_get(p_ptr)
        name = ffi.string(name_ptr).decode() if name_ptr != ffi.NULL else ""

        type_ptr = lib.p4tc_runt_param_attrs_type_name_get(p_ptr)
        type_name = ffi.string(type_ptr).decode() \
            if type_ptr != ffi.NULL else None

        sz_out = ffi.new("uint32_t *")
        val_ptr = lib.p4tc_runt_param_attrs_value_get(p_ptr, sz_out)
        sz = sz_out[0]
        value = bytes(ffi.buffer(val_ptr, sz)) \
            if val_ptr != ffi.NULL and sz > 0 else b""

        return Param(name=name, value=value, size=sz, type_name=type_name)

    @staticmethod
    def _parse_action(lib, a_ptr, entry_ptr):
        name_ptr = lib.p4tc_runt_act_attrs_name_get(a_ptr)
        name = ffi.string(name_ptr).decode() if name_ptr != ffi.NULL else ""
        index = lib.p4tc_runt_act_attrs_index_get(a_ptr)

        params = {}
        p = lib.p4tc_runt_act_attrs_param_first(a_ptr)
        while p != ffi.NULL:
            param = Context._parse_param(lib, p)
            params[param.name] = param
            p = lib.p4tc_runt_act_attrs_param_next(a_ptr, p)

        return Action(name=name, index=index, params=params)

    @staticmethod
    def _parse_entry(lib, e_ptr):
        name_ptr = lib.p4tc_runt_tbl_attrs_name_get(e_ptr)
        table_name = ffi.string(name_ptr).decode() \
            if name_ptr != ffi.NULL else None

        priority = lib.p4tc_runt_tbl_attrs_prio_get(e_ptr)

        keysz_out = ffi.new("uint32_t *")
        key_ptr = lib.p4tc_runt_tbl_attrs_key_get(e_ptr, keysz_out)
        key_size = keysz_out[0]
        key_bytes = bytes(ffi.buffer(key_ptr, key_size)) \
            if key_ptr != ffi.NULL and key_size > 0 else b""

        mask_ptr = lib.p4tc_runt_tbl_attrs_mask_get(e_ptr, keysz_out)
        mask_bytes = bytes(ffi.buffer(mask_ptr, keysz_out[0])) \
            if mask_ptr != ffi.NULL and keysz_out[0] > 0 else None

        permissions = lib.p4tc_runt_tbl_attrs_perms_get(e_ptr)
        dynamic = bool(lib.p4tc_runt_tbl_attrs_dyn_get(e_ptr))
        aging = lib.p4tc_runt_tbl_attrs_aging_get(e_ptr)

        actions = []
        a = lib.p4tc_runt_tbl_attrs_act_first(e_ptr)
        while a != ffi.NULL:
            actions.append(Context._parse_action(lib, a, e_ptr))
            a = lib.p4tc_runt_tbl_attrs_act_next(e_ptr, a)

        return TableEntry(
            table_name=table_name, priority=priority,
            key_bytes=key_bytes, key_size=key_size,
            mask_bytes=mask_bytes, permissions=permissions,
            dynamic=dynamic, aging=aging, actions=actions,
        )

    def _parse_obj(self, obj_ptr):
        lib = self._lib
        entries = []
        e = lib.p4tc_obj_tbl_entry_first(obj_ptr)
        while e != ffi.NULL:
            entries.append(self._parse_entry(lib, e))
            e = lib.p4tc_obj_tbl_entry_next(obj_ptr, e)
        return entries

    @staticmethod
    def _parse_extern(lib, x_ptr):
        kind_ptr = lib.p4tc_runt_ext_attrs_kind_get(x_ptr)
        kind = ffi.string(kind_ptr).decode() \
            if kind_ptr != ffi.NULL else None

        inst_ptr = lib.p4tc_runt_ext_attrs_inst_get(x_ptr)
        instance = ffi.string(inst_ptr).decode() \
            if inst_ptr != ffi.NULL else None

        key = lib.p4tc_runt_ext_attrs_key_get(x_ptr)
        ext_id = lib.p4tc_runt_ext_attrs_ext_id_get(x_ptr)
        inst_id = lib.p4tc_runt_ext_attrs_inst_id_get(x_ptr)

        params = {}
        p = lib.p4tc_runt_ext_attrs_param_first(x_ptr)
        while p != ffi.NULL:
            param = Context._parse_param(lib, p)
            params[param.name] = param
            p = lib.p4tc_runt_ext_attrs_param_next(x_ptr, p)

        return ExternEntry(kind=kind, instance=instance, key=key,
                           ext_id=ext_id, inst_id=inst_id, params=params)

    def _parse_ext_obj(self, obj_ptr):
        lib = self._lib
        entries = []
        x = lib.p4tc_obj_ext_first(obj_ptr)
        while x != ffi.NULL:
            entries.append(self._parse_extern(lib, x))
            x = lib.p4tc_obj_ext_next(obj_ptr, x)
        return entries

    @property
    def is_valid(self):
        return self._ctx is not None and self._ctx != ffi.NULL

    def destroy(self):
        if self._ctx is not None and self._ctx != ffi.NULL:
            for sub in self._subscriptions:
                sub.stop()
            self._subscriptions.clear()
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

        # String buffers must outlive the obj (library stores pointers).
        _keep = []

        pname_buf = ffi.new("char[]", pipeline.encode())
        _keep.append(pname_buf)

        obj = lib.p4tc_obj_create(pname_buf, int(ObjType.TABLE))
        if obj == ffi.NULL:
            raise ObjectError(f"obj_create failed for '{pipeline}'",
                              errno=_capture_errno())

        try:
            tname_buf = ffi.new("char[]", table.encode())
            _keep.append(tname_buf)
            lib.p4tc_obj_objname_set(obj, tname_buf)

            if filter_str is not None:
                fstr_buf = ffi.new("char[]", filter_str.encode())
                _keep.append(fstr_buf)
                lib.p4tc_obj_filter_set(obj, fstr_buf)

            if key is not None:
                if isinstance(key, dict):
                    if table_schema is not None:
                        key_values = table_schema.validate_key(key)
                    else:
                        key_values = list(key.values())
                else:
                    key_values = list(key)

                key_ptrs = [ffi.new("char[]", v.encode()) for v in key_values]
                _keep.extend(key_ptrs)
                key_arr = ffi.new("const char *[]", key_ptrs)
                _keep.append(key_arr)
                raw_key = lib.p4tc_make_key(obj, len(key_values), key_arr)
                if raw_key == ffi.NULL:
                    raise KeyError_(f"make_key failed for {key}",
                                    errno=_capture_errno())

                # key ownership transfers to obj via alloc_tbl_entry
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

                if action is not None:
                    self._attach_action(lib, entry, action, table_schema,
                                        _keep)

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
                self._attach_action(lib, entry, action, table_schema, _keep)

            ret = crud_fn(self._ctx, obj, int(flags), ffi.NULL, ffi.NULL)
            if ret != 0:
                raise CRUDError(f"CRUD failed on '{pipeline}/{table}'",
                                errno=_capture_errno())
            return ret
        finally:
            lib.p4tc_obj_destroy(obj)
            del _keep

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

    def _attach_action(self, lib, entry, action, table_schema, _keep):
        """Parse and attach an action to a table entry."""
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
        _keep.extend(param_ptrs)
        param_arr = ffi.new("const char *[]", param_ptrs)
        _keep.append(param_arr)
        act_path_buf = ffi.new("char[]", act_path.encode())
        _keep.append(act_path_buf)
        act = lib.p4tc_create_runt_act(entry, act_path_buf,
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
        self._build_and_send(self._lib.p4tc_create, pipeline, table,
                             key=key, action=action, priority=priority,
                             entity=entity, flags=int(flags),
                             aging_ms=aging_ms, profile_id=profile_id,
                             permissions=permissions, dynamic=dynamic)

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
        self._build_and_send(self._lib.p4tc_update, pipeline, table,
                             key=key, action=action, filter_str=filter_str,
                             priority=priority, entity=entity, flags=int(flags),
                             aging_ms=aging_ms, profile_id=profile_id,
                             permissions=permissions, dynamic=dynamic)

    def get(self, pipeline, table, *, key=None,
            filter_str=None, flags=0):
        """Read table entries.

        *key* given → single entry; returns a ``TableEntry`` or ``None``.
        *key* omitted → all entries; returns a ``list[TableEntry]``.
        """
        captured = []

        def _capture_cb(obj_ptr, ctx_ptr, cookie_ptr, phase_val):
            try:
                phase = Phase(phase_val)
                if phase in (Phase.SOT, Phase.MOT) and obj_ptr != ffi.NULL:
                    captured.extend(self._parse_obj(obj_ptr))
                return 0
            except Exception:
                return -1

        c_cb = ffi.callback(
            "int(const struct p4tc_obj*, struct p4tc_runt_ctx*,"
            " uint64_t*, int)",
            _capture_cb,
        )

        lib = self._lib
        schema = _get_schema(pipeline)
        table_schema = schema.get_table(table) if schema else None
        _keep = []

        pname_buf = ffi.new("char[]", pipeline.encode())
        _keep.append(pname_buf)
        obj = lib.p4tc_obj_create(pname_buf, int(ObjType.TABLE))
        if obj == ffi.NULL:
            raise ObjectError(f"obj_create failed for '{pipeline}'",
                              errno=_capture_errno())

        try:
            tname_buf = ffi.new("char[]", table.encode())
            _keep.append(tname_buf)
            lib.p4tc_obj_objname_set(obj, tname_buf)

            if filter_str is not None:
                filt_buf = ffi.new("char[]", filter_str.encode())
                _keep.append(filt_buf)
                lib.p4tc_obj_filter_set(obj, filt_buf)

            if key is not None:
                if isinstance(key, dict):
                    key_values = table_schema.validate_key(key) \
                        if table_schema else list(key.values())
                else:
                    key_values = list(key)

                key_ptrs = [ffi.new("char[]", v.encode())
                            for v in key_values]
                _keep.extend(key_ptrs)
                key_arr = ffi.new("const char *[]", key_ptrs)
                _keep.append(key_arr)
                raw_key = lib.p4tc_make_key(obj, len(key_values), key_arr)
                if raw_key == ffi.NULL:
                    raise KeyError_(f"make_key failed for {key}",
                                   errno=_capture_errno())
                entry = lib.p4tc_alloc_tbl_entry(obj, raw_key,
                                                 0, int(Entity.TC))
                if entry == ffi.NULL:
                    raise EntryError(
                        f"alloc_tbl_entry failed for '{table}'",
                        errno=_capture_errno())

            ret = lib.p4tc_get(self._ctx, obj, int(flags), c_cb, ffi.NULL)
            if ret != 0:
                raise CRUDError(f"get failed on '{pipeline}/{table}'",
                                errno=_capture_errno())
        finally:
            lib.p4tc_obj_destroy(obj)
            del _keep

        if key is not None and filter_str is None:
            return captured[0] if captured else None
        return captured

    def dump(self, pipeline, table, *, filter_str=None):
        """Dump all entries from a table.

        Returns a ``list[TableEntry]``.
        """
        return self.get(pipeline, table,
                        filter_str=filter_str)

    def delete(self, pipeline, table, *, key=None,
               filter_str=None, flags=0):
        """Delete entry/entries from a table."""
        self._build_and_send(self._lib.p4tc_del, pipeline, table,
                             key=key, filter_str=filter_str, flags=int(flags))

    def flush(self, pipeline, table, *, flags=0):
        """Delete all entries from a table."""
        self.delete(pipeline, table, flags=flags)


    def _build_extern_obj(self, pipeline, kind, instance, key,
                          params=None):
        """Build a p4tc_obj for an extern operation.

        Returns (obj, _keep) where _keep pins string buffers.
        """
        lib = self._lib
        _keep = []

        pname_buf = ffi.new("char[]", pipeline.encode())
        _keep.append(pname_buf)

        obj = lib.p4tc_obj_create(pname_buf, int(ObjType.EXTERN))
        if obj == ffi.NULL:
            raise ObjectError(f"obj_create failed for '{pipeline}'",
                              errno=_capture_errno())

        param_values = list(params.values()) if isinstance(params, dict) \
            else list(params or [])

        param_ptrs = [ffi.new("char[]", p.encode()) for p in param_values]
        _keep.extend(param_ptrs)
        param_arr = ffi.new("const char *[]", param_ptrs) \
            if param_ptrs else ffi.NULL
        if param_arr != ffi.NULL:
            _keep.append(param_arr)

        kind_buf = ffi.new("char[]", kind.encode())
        inst_buf = ffi.new("char[]", instance.encode())
        _keep.extend([kind_buf, inst_buf])

        ext = lib.p4tc_create_runt_ext(
            obj, kind_buf, inst_buf,
            key, len(param_values), param_arr,
        )
        if ext == ffi.NULL:
            lib.p4tc_obj_destroy(obj)
            raise EntryError(
                f"create_runt_ext failed for '{kind}/{instance}'",
                errno=_capture_errno())

        return obj, _keep

    def extern_insert(self, pipeline, kind, instance, *, key,
                      params=None, flags=0):
        """Create an extern instance entry."""
        obj, _keep = self._build_extern_obj(pipeline, kind, instance,
                                            key, params)
        try:
            ret = self._lib.p4tc_create(self._ctx, obj, int(flags),
                                        ffi.NULL, ffi.NULL)
            if ret != 0:
                raise CRUDError(
                    f"extern create failed for '{kind}/{instance}'",
                    errno=_capture_errno())
        finally:
            self._lib.p4tc_obj_destroy(obj)
            del _keep

    def extern_update(self, pipeline, kind, instance, *, key,
                      params=None, flags=0):
        """Update an extern instance entry."""
        obj, _keep = self._build_extern_obj(pipeline, kind, instance,
                                            key, params)
        try:
            ret = self._lib.p4tc_update(self._ctx, obj, int(flags),
                                        ffi.NULL, ffi.NULL)
            if ret != 0:
                raise CRUDError(
                    f"extern update failed for '{kind}/{instance}'",
                    errno=_capture_errno())
        finally:
            self._lib.p4tc_obj_destroy(obj)
            del _keep

    def extern_get(self, pipeline, kind, instance, *, key,
                   flags=0):
        """Read an extern instance entry.

        Returns an ``ExternEntry`` or ``None``.
        """
        captured = []

        def _capture_cb(obj_ptr, ctx_ptr, cookie_ptr, phase_val):
            try:
                phase = Phase(phase_val)
                if phase in (Phase.SOT, Phase.MOT) and obj_ptr != ffi.NULL:
                    captured.extend(self._parse_ext_obj(obj_ptr))
                return 0
            except Exception:
                return -1

        c_cb = ffi.callback(
            "int(const struct p4tc_obj*, struct p4tc_runt_ctx*,"
            " uint64_t*, int)",
            _capture_cb,
        )

        obj, _keep = self._build_extern_obj(pipeline, kind, instance, key)
        try:
            ret = self._lib.p4tc_get(self._ctx, obj, int(flags),
                                     c_cb, ffi.NULL)
            if ret != 0:
                raise CRUDError(
                    f"extern get failed for '{kind}/{instance}'",
                    errno=_capture_errno())
        finally:
            self._lib.p4tc_obj_destroy(obj)
            del _keep

        return captured[0] if captured else None

    def extern_delete(self, pipeline, kind, instance, *, key, flags=0):
        """Delete an extern instance entry."""
        obj, _keep = self._build_extern_obj(pipeline, kind, instance, key)
        try:
            ret = self._lib.p4tc_del(self._ctx, obj, int(flags),
                                     ffi.NULL, ffi.NULL)
            if ret != 0:
                raise CRUDError(
                    f"extern delete failed for '{kind}/{instance}'",
                    errno=_capture_errno())
        finally:
            self._lib.p4tc_obj_destroy(obj)
            del _keep

    def subscribe(self, pipeline, table, *, callback, filter_str=None):
        """Subscribe to events on a table.

        Returns a Subscription that listens in a background thread.
        Use as a context manager or call start()/stop() manually.

        ``callback(entry: TableEntry, phase: Phase)`` is called
        for each event.
        """
        sub = Subscription(self._lib, self._parse_obj,
                           pipeline, table, callback, filter_str)
        self._subscriptions.append(sub)
        return sub


class Subscription:
    """Background listener for table events.

    Creates its own netlink context so the parent Context can be
    destroyed independently.

    Use as a context manager::

        with ctx.subscribe('pipe', 'ingress/t', callback=fn) as sub:
            time.sleep(60)  # fn fires in background
    """

    def __init__(self, lib, parse_obj_fn,
                 pipeline, table, callback, filter_str=None):
        self._lib = lib
        self._parse_obj = parse_obj_fn
        self._pipeline = pipeline
        self._table = table
        self._user_cb = callback
        self._filter_str = filter_str
        self._running = False
        self._thread = None
        self._c_cb = None

    @property
    def active(self):
        return (self._running
                and self._thread is not None
                and self._thread.is_alive())

    def start(self):
        """Start listening in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the listener to stop after the current event batch."""
        self._running = False

    def _run(self):
        lib = self._lib
        user_cb = self._user_cb
        parse_obj = self._parse_obj

        sub_ctx = lib.p4tc_runt_ctx_create(int(Transport.NETLINK))
        if sub_ctx == ffi.NULL:
            return

        @ffi.callback(
            "int(const struct p4tc_obj*, struct p4tc_runt_ctx*,"
            " uint64_t*, int)")
        def _on_event(obj_ptr, ctx_ptr, cookie_ptr, phase_val):
            try:
                phase = Phase(phase_val)
                if phase in (Phase.SOT, Phase.MOT) \
                        and obj_ptr != ffi.NULL:
                    for entry in parse_obj(obj_ptr):
                        user_cb(entry, phase)
                return 0
            except Exception:
                return -1

        self._c_cb = _on_event

        try:
            while self._running:
                obj = lib.p4tc_obj_create(
                    self._pipeline.encode(), int(ObjType.TABLE))
                if obj == ffi.NULL:
                    break
                try:
                    lib.p4tc_obj_objname_set(
                        obj, self._table.encode())
                    if self._filter_str:
                        filt = ffi.new(
                            "char[]", self._filter_str.encode())
                        lib.p4tc_obj_filter_set(obj, filt)
                    lib.p4tc_subscribe(
                        sub_ctx, obj, 0,
                        _on_event, ffi.NULL)
                finally:
                    lib.p4tc_obj_destroy(obj)
        finally:
            lib.p4tc_runt_ctx_destroy(sub_ctx)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def __repr__(self):
        state = "active" if self.active else "stopped"
        return f"Subscription({self._table!r}, {state})"

