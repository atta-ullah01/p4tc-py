"""Tests for Context: CRUD flow, callback plumbing, response phases."""

import pytest

from p4tc._ffi import ffi
from p4tc.context import Context, Subscription
from p4tc.entry import Action, ExternEntry, Param, TableEntry
from p4tc.errors import EntryError, SubscribeError
from p4tc.types import MsgFlags, Phase



class TestCallbackSetup:
    """Default callback is registered eagerly on init."""

    def test_callback_registered_on_init(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        mock_lib.p4tc_runt_ctx_dflt_cb_set.assert_called_once()
        assert ctx._c_callback is not None
        ctx.destroy()

    def test_dump_uses_root_flag(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.dump("pipe", "t")
        # dump sends p4tc_get with ROOT, then p4tc_dump_handle
        mock_lib.p4tc_get.assert_called_once()
        mock_lib.p4tc_dump_handle.assert_called_once()
        ctx.destroy()

    def test_initial_state(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        assert ctx._responses == []
        assert ctx._aborted is False
        assert ctx._user_cb is None
        ctx.destroy()


class TestResponsePhases:
    """_on_response should handle each transaction phase correctly."""

    def test_sot_appends_obj(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        obj = ffi.cast("void *", 42)
        assert ctx._on_response(obj, ffi.NULL, ffi.NULL, Phase.SOT) == 0
        assert len(ctx._responses) == 1
        ctx.destroy()

    def test_mot_appends_obj(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        obj = ffi.cast("void *", 42)
        assert ctx._on_response(obj, ffi.NULL, ffi.NULL, Phase.MOT) == 0
        assert len(ctx._responses) == 1
        ctx.destroy()

    def test_eot_is_noop(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        assert ctx._on_response(ffi.NULL, ffi.NULL, ffi.NULL, Phase.EOT) == 0
        assert len(ctx._responses) == 0
        ctx.destroy()

    def test_abt_sets_aborted(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        assert ctx._on_response(ffi.NULL, ffi.NULL, ffi.NULL, Phase.ABT) == -1
        assert ctx._aborted is True
        ctx.destroy()

    def test_reset_clears_state(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx._on_response(ffi.cast("void *", 1), ffi.NULL, ffi.NULL, Phase.SOT)
        ctx._aborted = True

        ctx._reset_response_state()
        assert ctx._responses == []
        assert ctx._aborted is False
        ctx.destroy()


class TestUserCallback:
    """When _user_cb is set, it should receive forwarded events."""

    def test_forwarded_on_sot_and_mot(self, mock_lib):
        ctx = Context(_lib=mock_lib)

        received = []
        ctx._user_cb = lambda obj, phase: received.append(phase)

        obj = ffi.cast("void *", 99)
        ctx._on_response(obj, ffi.NULL, ffi.NULL, Phase.SOT)
        ctx._on_response(obj, ffi.NULL, ffi.NULL, Phase.MOT)

        assert received == [Phase.SOT, Phase.MOT]
        ctx.destroy()



class TestResponseHandling:
    """Verify that CRUD methods call p4tc_resp_handle when appropriate."""

    def test_get_calls_p4tc_get_directly(self, mock_lib):
        """get() builds its own obj and passes a callback to p4tc_get."""
        ctx = Context(_lib=mock_lib)
        ctx.get("pipe", "ingress/t")
        mock_lib.p4tc_get.assert_called_once()
        mock_lib.p4tc_resp_handle.assert_not_called()
        ctx.destroy()

    def test_insert_skips_resp_handle_by_default(self, mock_lib):
        """insert() defaults to flags=0, so no resp_handle."""
        ctx = Context(_lib=mock_lib)
        ctx.insert("pipe", "ingress/t",
                   key={"k": "v"}, action=("act", {"p": "v"}))
        mock_lib.p4tc_resp_handle.assert_not_called()
        ctx.destroy()


class TestFilter:

    def test_get_with_filter(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.get("pipe", "t", filter_str='param.act.a.p = "v"')
        mock_lib.p4tc_obj_filter_set.assert_called_once()
        ctx.destroy()

    def test_get_with_filter_returns_list(self, mock_lib):
        """filter_str forces list return even if key is also given."""
        ctx = Context(_lib=mock_lib)
        result = ctx.get("pipe", "t", key={"k": "v"},
                         filter_str='param.act.a.p = "v"')
        assert isinstance(result, list)
        ctx.destroy()

    def test_update_with_filter(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.update("pipe", "t", action=("a", {"p": "v"}),
                   filter_str='param.act.a.p = "old"')
        mock_lib.p4tc_obj_filter_set.assert_called_once()
        ctx.destroy()

    def test_delete_with_filter(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.delete("pipe", "t", filter_str='param.act.a.port_id = "port0"')
        mock_lib.p4tc_obj_filter_set.assert_called_once()
        ctx.destroy()

    def test_dump_with_filter(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.dump("pipe", "t", filter_str='param.act.a.p = "v"')
        mock_lib.p4tc_obj_filter_set.assert_called_once()
        ctx.destroy()

    def test_no_filter_by_default(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.get("pipe", "t")
        mock_lib.p4tc_obj_filter_set.assert_not_called()
        ctx.destroy()


class TestEntryAttributes:
    """Optional kwargs on insert/update should call the right C setters."""

    def test_no_attrs_by_default(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.insert("p", "t", key={"k": "v"}, action=("a", {"p": "v"}))

        mock_lib.p4tc_runt_tbl_attrs_aging_set.assert_not_called()
        mock_lib.p4tc_runt_tbl_attrs_profile_id_set.assert_not_called()
        mock_lib.p4tc_runt_tbl_attrs_perms_set.assert_not_called()
        mock_lib.p4tc_runt_tbl_attrs_dyn_set.assert_not_called()
        ctx.destroy()

    def test_aging_ms(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.insert("p", "t", key={"k": "v"}, action=("a", {"p": "v"}),
                   aging_ms=5000)
        mock_lib.p4tc_runt_tbl_attrs_aging_set.assert_called_once_with(
            ffi.cast("void *", 30), 5000)
        ctx.destroy()

    def test_profile_id(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.insert("p", "t", key={"k": "v"}, action=("a", {"p": "v"}),
                   profile_id=7)
        mock_lib.p4tc_runt_tbl_attrs_profile_id_set.assert_called_once_with(
            ffi.cast("void *", 30), 7)
        ctx.destroy()

    def test_permissions(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.insert("p", "t", key={"k": "v"}, action=("a", {"p": "v"}),
                   permissions=0x3CA6)
        mock_lib.p4tc_runt_tbl_attrs_perms_set.assert_called_once_with(
            ffi.cast("void *", 30), 0x3CA6)
        ctx.destroy()

    def test_dynamic_true_sends_1(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.insert("p", "t", key={"k": "v"}, action=("a", {"p": "v"}),
                   dynamic=True)
        mock_lib.p4tc_runt_tbl_attrs_dyn_set.assert_called_once_with(
            ffi.cast("void *", 30), 1)
        ctx.destroy()

    def test_dynamic_false_sends_0(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.insert("p", "t", key={"k": "v"}, action=("a", {"p": "v"}),
                   dynamic=False)
        mock_lib.p4tc_runt_tbl_attrs_dyn_set.assert_called_once_with(
            ffi.cast("void *", 30), 0)
        ctx.destroy()

    def test_all_attrs_at_once(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.insert("p", "t", key={"k": "v"}, action=("a", {"p": "v"}),
                   priority=10, aging_ms=3000, permissions=0xFF,
                   dynamic=True, profile_id=2)

        mock_lib.p4tc_runt_tbl_attrs_prio_set.assert_called_once()
        mock_lib.p4tc_runt_tbl_attrs_aging_set.assert_called_once()
        mock_lib.p4tc_runt_tbl_attrs_perms_set.assert_called_once()
        mock_lib.p4tc_runt_tbl_attrs_dyn_set.assert_called_once()
        mock_lib.p4tc_runt_tbl_attrs_profile_id_set.assert_called_once()
        ctx.destroy()

    def test_update_also_passes_attrs(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.update("p", "t", key={"k": "v"}, action=("a", {"p": "v"}),
                   aging_ms=1000)
        mock_lib.p4tc_runt_tbl_attrs_aging_set.assert_called_once()
        ctx.destroy()


class TestExternCRUD:
    """extern_insert/update/get/delete should call the right C functions."""

    def test_extern_insert_calls_create(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.extern_insert("pipe", "Counter", "ingress/bytes", key=1,
                          params={"packets": "0", "bytes": "0"})
        mock_lib.p4tc_create_runt_ext.assert_called_once()
        mock_lib.p4tc_create.assert_called_once()
        ctx.destroy()

    def test_extern_insert_uses_extern_obj_type(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.extern_insert("pipe", "Counter", "ingress/bytes", key=1)
        # ObjType.EXTERN == 2
        args = mock_lib.p4tc_obj_create.call_args[0]
        assert args[1] == 2
        ctx.destroy()

    def test_extern_update_calls_update(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.extern_update("pipe", "Counter", "ingress/bytes", key=1,
                          params={"packets": "100"})
        mock_lib.p4tc_update.assert_called_once()
        ctx.destroy()

    def test_extern_get_calls_get(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.extern_get("pipe", "Counter", "ingress/bytes", key=1)
        mock_lib.p4tc_get.assert_called_once()
        ctx.destroy()

    def test_extern_get_empty_returns_none(self, mock_lib):
        mock_lib.p4tc_obj_ext_first.return_value = ffi.NULL
        ctx = Context(_lib=mock_lib)
        result = ctx.extern_get("pipe", "Counter", "ingress/bytes", key=1)
        assert result is None
        ctx.destroy()

    def test_extern_delete_calls_del(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.extern_delete("pipe", "Counter", "ingress/bytes", key=1)
        mock_lib.p4tc_del.assert_called_once()
        ctx.destroy()

    def test_extern_insert_no_params(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.extern_insert("pipe", "Counter", "ingress/bytes", key=42)
        mock_lib.p4tc_create_runt_ext.assert_called_once()
        ctx.destroy()

    def test_extern_create_failure_raises(self, mock_lib):
        mock_lib.p4tc_create_runt_ext.return_value = ffi.NULL
        ctx = Context(_lib=mock_lib)
        with pytest.raises(EntryError, match="create_runt_ext"):
            ctx.extern_insert("pipe", "Counter", "ingress/bytes", key=1)
        ctx.destroy()


class TestSubscribe:
    """subscribe/unsubscribe should call the right C functions."""

    def test_subscribe_returns_subscription(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        sub = ctx.subscribe("pipe", "ingress/t")
        assert isinstance(sub, Subscription)
        assert sub.sub_id == 1
        mock_lib.p4tc_subscribe.assert_called_once()
        ctx.destroy()

    def test_subscribe_failure_raises(self, mock_lib):
        mock_lib.p4tc_subscribe.return_value = -1
        ctx = Context(_lib=mock_lib)
        with pytest.raises(SubscribeError, match="subscribe failed"):
            ctx.subscribe("pipe", "ingress/t")
        ctx.destroy()

    def test_unsubscribe_calls_c_api(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        sub = ctx.subscribe("pipe", "ingress/t")
        sub.unsubscribe()
        mock_lib.p4tc_unsubscribe.assert_called_once_with(
            ctx._ctx, 1)
        ctx.destroy()

    def test_process_events_calls_resp_handle(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        sub = ctx.subscribe("pipe", "ingress/t")
        sub.process_events()
        mock_lib.p4tc_subscribe_resp_handle.assert_called_once_with(
            ctx._ctx, 1)
        ctx.destroy()

    def test_subscription_context_manager(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        with ctx.subscribe("pipe", "ingress/t") as sub:
            assert sub.sub_id == 1
        mock_lib.p4tc_unsubscribe.assert_called_once()
        ctx.destroy()

    def test_destroy_cleans_up_subscriptions(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.subscribe("pipe", "ingress/t")
        ctx.destroy()
        mock_lib.p4tc_unsubscribe.assert_called_once()

    def test_subscribe_with_callback(self, mock_lib):
        received = []
        ctx = Context(_lib=mock_lib)
        ctx.subscribe("pipe", "ingress/t",
                      callback=lambda obj, phase: received.append(phase))
        mock_lib.p4tc_subscribe.assert_called_once()
        ctx.destroy()

    def test_unsubscribe_idempotent(self, mock_lib):
        """Calling unsubscribe twice should not raise."""
        ctx = Context(_lib=mock_lib)
        sub = ctx.subscribe("pipe", "ingress/t")
        sub.unsubscribe()
        sub.unsubscribe()  # second call is a no-op
        ctx.destroy()


class TestParsing:
    """Verify that getter functions produce correct TableEntry objects."""

    @staticmethod
    def _stub_getters(lib, *,
                      table_name=b"ingress/nh_table",
                      priority=64000,
                      key_blob=b"\xc0\xa8\x01\x0a",
                      mask_blob=None,
                      permissions=0x3CA6,
                      dynamic=0,
                      aging=0,
                      action_name=b"ingress/send_nh",
                      action_index=1,
                      params=None):
        """Wire up mock getters so _parse_entry produces expected data."""
        # -- table entry pointers --
        entry_ptr = ffi.cast("void *", 100)
        act_ptr = ffi.cast("void *", 200)

        # obj iterators: one entry, then NULL
        lib.p4tc_obj_tbl_entry_first.return_value = entry_ptr
        lib.p4tc_obj_tbl_entry_next.return_value = ffi.NULL

        # table entry getters
        tname_buf = ffi.new("char[]", table_name)
        lib.p4tc_runt_tbl_attrs_name_get.return_value = tname_buf
        lib.p4tc_runt_tbl_attrs_prio_get.return_value = priority
        lib.p4tc_runt_tbl_attrs_perms_get.return_value = permissions
        lib.p4tc_runt_tbl_attrs_dyn_get.return_value = dynamic
        lib.p4tc_runt_tbl_attrs_aging_get.return_value = aging

        # key blob
        key_buf = ffi.new("uint8_t[]", key_blob)
        def _key_get(e, sz_ptr):
            sz_ptr[0] = len(key_blob)
            return key_buf
        lib.p4tc_runt_tbl_attrs_key_get.side_effect = _key_get

        # mask blob
        if mask_blob is not None:
            mask_buf = ffi.new("uint8_t[]", mask_blob)
            def _mask_get(e, sz_ptr):
                sz_ptr[0] = len(mask_blob)
                return mask_buf
            lib.p4tc_runt_tbl_attrs_mask_get.side_effect = _mask_get
        else:
            lib.p4tc_runt_tbl_attrs_mask_get.side_effect = \
                lambda e, sz: ffi.NULL

        # action iterator: one action, then NULL
        lib.p4tc_runt_tbl_attrs_act_first.return_value = act_ptr
        lib.p4tc_runt_tbl_attrs_act_next.return_value = ffi.NULL

        # action getters
        aname_buf = ffi.new("char[]", action_name)
        lib.p4tc_runt_act_attrs_name_get.return_value = aname_buf
        lib.p4tc_runt_act_attrs_index_get.return_value = action_index

        # param iterator + getters
        if params is None:
            params = [
                (b"port_id", b"dev", b"\x00\x00\x00\x01"),
                (b"dmac", b"macaddr", b"\x00\xaa\xbb\xcc\xdd\xee"),
            ]

        param_ptrs = [ffi.cast("void *", 300 + i)
                      for i in range(len(params))]
        # first/next chain
        lib.p4tc_runt_act_attrs_param_first.return_value = param_ptrs[0]
        next_map = {}
        for i in range(len(param_ptrs) - 1):
            next_map[int(ffi.cast("uintptr_t", param_ptrs[i]))] = \
                param_ptrs[i + 1]
        next_map[int(ffi.cast("uintptr_t", param_ptrs[-1]))] = ffi.NULL

        def _param_next(a, cur):
            addr = int(ffi.cast("uintptr_t", cur))
            return next_map.get(addr, ffi.NULL)
        lib.p4tc_runt_act_attrs_param_next.side_effect = _param_next

        # param getters keyed by pointer address
        name_bufs = [ffi.new("char[]", p[0]) for p in params]
        type_bufs = [ffi.new("char[]", p[1]) for p in params]
        val_bufs = [ffi.new("uint8_t[]", p[2]) for p in params]
        addr_to_idx = {
            int(ffi.cast("uintptr_t", pp)): i
            for i, pp in enumerate(param_ptrs)
        }

        def _pname_get(p):
            i = addr_to_idx.get(int(ffi.cast("uintptr_t", p)), 0)
            return name_bufs[i]
        lib.p4tc_runt_param_attrs_name_get.side_effect = _pname_get

        def _ptype_get(p):
            i = addr_to_idx.get(int(ffi.cast("uintptr_t", p)), 0)
            return type_bufs[i]
        lib.p4tc_runt_param_attrs_type_name_get.side_effect = _ptype_get

        def _pval_get(p, sz_ptr):
            i = addr_to_idx.get(int(ffi.cast("uintptr_t", p)), 0)
            sz_ptr[0] = len(params[i][2])
            return val_bufs[i]
        lib.p4tc_runt_param_attrs_value_get.side_effect = _pval_get

        # keep references alive for the duration of the test
        lib._test_refs = [tname_buf, key_buf, aname_buf,
                          name_bufs, type_bufs, val_bufs, param_ptrs]
        return entry_ptr

    def test_parse_param(self, mock_lib):
        self._stub_getters(mock_lib)
        ctx = Context(_lib=mock_lib)
        p_ptr = ffi.cast("void *", 300)
        param = ctx._parse_param(mock_lib, p_ptr)
        assert param.name == "port_id"
        assert param.type_name == "dev"
        assert param.value == b"\x00\x00\x00\x01"
        assert param.size == 4
        ctx.destroy()

    def test_parse_action(self, mock_lib):
        entry_ptr = self._stub_getters(mock_lib)
        ctx = Context(_lib=mock_lib)
        a_ptr = ffi.cast("void *", 200)
        action = ctx._parse_action(mock_lib, a_ptr, entry_ptr)
        assert action.name == "ingress/send_nh"
        assert action.index == 1
        assert "port_id" in action.params
        assert "dmac" in action.params
        ctx.destroy()

    def test_parse_entry(self, mock_lib):
        self._stub_getters(mock_lib)
        ctx = Context(_lib=mock_lib)
        entry_ptr = ffi.cast("void *", 100)
        entry = ctx._parse_entry(mock_lib, entry_ptr)
        assert entry.table_name == "ingress/nh_table"
        assert entry.priority == 64000
        assert entry.key_bytes == b"\xc0\xa8\x01\x0a"
        assert entry.key_size == 4
        assert entry.permissions == 0x3CA6
        assert len(entry.actions) == 1
        ctx.destroy()

    def test_parse_obj_walks_entries(self, mock_lib):
        self._stub_getters(mock_lib)
        ctx = Context(_lib=mock_lib)
        obj_ptr = ffi.cast("void *", 10)
        entries = ctx._parse_obj(obj_ptr)
        assert len(entries) == 1
        assert isinstance(entries[0], TableEntry)
        ctx.destroy()

    def test_parse_obj_empty(self, mock_lib):
        mock_lib.p4tc_obj_tbl_entry_first.return_value = ffi.NULL
        ctx = Context(_lib=mock_lib)
        entries = ctx._parse_obj(ffi.cast("void *", 10))
        assert entries == []
        ctx.destroy()

    def test_get_returns_table_entry(self, mock_lib):
        """get() with a key should return a single TableEntry."""
        from p4tc.types import Phase
        entry_ptr = self._stub_getters(mock_lib)

        # Make p4tc_get invoke the callback with SOT phase
        obj_ptr_for_cb = ffi.cast("void *", 10)
        def _get_with_cb(ctx, obj, flags, cb, cookie):
            cb(obj_ptr_for_cb, ctx, ffi.NULL, int(Phase.SOT))
            return 0
        mock_lib.p4tc_get.side_effect = _get_with_cb

        ctx = Context(_lib=mock_lib)
        result = ctx.get("pipe", "ingress/nh_table",
                         key={"srcAddr": "192.168.1.10"})
        assert isinstance(result, TableEntry)
        assert result.table_name == "ingress/nh_table"
        assert result.priority == 64000
        assert len(result.actions) == 1
        assert result.actions[0].name == "ingress/send_nh"
        ctx.destroy()

    def test_get_no_key_returns_list(self, mock_lib):
        """get() without a key returns a list of entries."""
        from p4tc.types import Phase
        self._stub_getters(mock_lib)

        obj_ptr_for_cb = ffi.cast("void *", 10)
        def _get_with_cb(ctx, obj, flags, cb, cookie):
            cb(obj_ptr_for_cb, ctx, ffi.NULL, int(Phase.SOT))
            return 0
        mock_lib.p4tc_get.side_effect = _get_with_cb

        ctx = Context(_lib=mock_lib)
        result = ctx.get("pipe", "ingress/nh_table")
        assert isinstance(result, list)
        assert len(result) == 1
        ctx.destroy()

    def test_get_empty_response(self, mock_lib):
        """get() with key but no response returns None."""
        mock_lib.p4tc_obj_tbl_entry_first.return_value = ffi.NULL
        ctx = Context(_lib=mock_lib)
        result = ctx.get("pipe", "ingress/nh_table",
                         key={"srcAddr": "192.168.1.10"})
        assert result is None
        ctx.destroy()

    def test_dump_returns_list(self, mock_lib):
        self._stub_getters(mock_lib)

        obj_ptr_for_cb = ffi.cast("void *", 10)
        def _get_with_cb(ctx, obj, flags, cb, cookie):
            cb(obj_ptr_for_cb, ctx, ffi.NULL, int(Phase.SOT))
            return 0
        mock_lib.p4tc_get.side_effect = _get_with_cb

        ctx = Context(_lib=mock_lib)
        result = ctx.dump("pipe", "ingress/nh_table")
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TableEntry)
        ctx.destroy()

    def test_dump_empty_table(self, mock_lib):
        mock_lib.p4tc_obj_tbl_entry_first.return_value = ffi.NULL
        ctx = Context(_lib=mock_lib)
        result = ctx.dump("pipe", "ingress/nh_table")
        assert result == []
        ctx.destroy()

    @staticmethod
    def _stub_extern_getters(lib):
        """Wire mock getters for a single extern entry."""
        ext_ptr = ffi.cast("void *", 500)
        lib.p4tc_obj_ext_first.return_value = ext_ptr
        lib.p4tc_obj_ext_next.return_value = ffi.NULL

        kind_buf = ffi.new("char[]", b"Counter")
        inst_buf = ffi.new("char[]", b"ingress/bytes")
        lib.p4tc_runt_ext_attrs_kind_get.return_value = kind_buf
        lib.p4tc_runt_ext_attrs_inst_get.return_value = inst_buf
        lib.p4tc_runt_ext_attrs_key_get.return_value = 42
        lib.p4tc_runt_ext_attrs_ext_id_get.return_value = 1
        lib.p4tc_runt_ext_attrs_inst_id_get.return_value = 2

        # one param
        p_ptr = ffi.cast("void *", 600)
        lib.p4tc_runt_ext_attrs_param_first.return_value = p_ptr
        lib.p4tc_runt_ext_attrs_param_next.return_value = ffi.NULL

        pname = ffi.new("char[]", b"packets")
        ptype = ffi.new("char[]", b"bit32")
        pval = ffi.new("uint8_t[]", b"\x00\x00\x00\x64")
        lib.p4tc_runt_param_attrs_name_get.side_effect = lambda p: pname
        lib.p4tc_runt_param_attrs_type_name_get.side_effect = lambda p: ptype
        def _val_get(p, sz_ptr):
            sz_ptr[0] = 4
            return pval
        lib.p4tc_runt_param_attrs_value_get.side_effect = _val_get

        lib._test_ext_refs = [kind_buf, inst_buf, pname, ptype, pval]
        return ext_ptr

    def test_parse_extern(self, mock_lib):
        self._stub_extern_getters(mock_lib)
        ctx = Context(_lib=mock_lib)
        x_ptr = ffi.cast("void *", 500)
        entry = ctx._parse_extern(mock_lib, x_ptr)
        assert isinstance(entry, ExternEntry)
        assert entry.kind == "Counter"
        assert entry.instance == "ingress/bytes"
        assert entry.key == 42
        assert "packets" in entry.params
        assert entry.params["packets"].value == b"\x00\x00\x00\x64"
        ctx.destroy()

    def test_extern_get_returns_entry(self, mock_lib):
        self._stub_extern_getters(mock_lib)

        obj_ptr_for_cb = ffi.cast("void *", 10)
        def _get_with_cb(ctx, obj, flags, cb, cookie):
            cb(obj_ptr_for_cb, ctx, ffi.NULL, int(Phase.SOT))
            return 0
        mock_lib.p4tc_get.side_effect = _get_with_cb

        ctx = Context(_lib=mock_lib)
        result = ctx.extern_get("pipe", "Counter", "ingress/bytes", key=42)
        assert isinstance(result, ExternEntry)
        assert result.kind == "Counter"
        assert result.key == 42
        ctx.destroy()
