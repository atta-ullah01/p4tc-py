"""Tests for Context: CRUD flow, callback plumbing, response phases."""

import pytest

from p4tc._ffi import ffi
from p4tc.context import Context
from p4tc.errors import EntryError
from p4tc.types import MsgFlags, Phase



class TestCallbackSetup:
    """Context.__init__ should wire up a default cffi callback."""

    def test_registers_callback_on_init(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        mock_lib.p4tc_runt_ctx_dflt_cb_set.assert_called_once()
        _, cb = mock_lib.p4tc_runt_ctx_dflt_cb_set.call_args[0]
        assert cb is ctx._c_callback
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

    def test_get_calls_resp_handle_by_default(self, mock_lib):
        """get() defaults to ECHO, so resp_handle should fire."""
        ctx = Context(_lib=mock_lib)
        ctx.get("pipe", "ingress/t")
        mock_lib.p4tc_resp_handle.assert_called_once()
        ctx.destroy()

    def test_insert_skips_resp_handle_by_default(self, mock_lib):
        """insert() defaults to flags=0, so no resp_handle."""
        ctx = Context(_lib=mock_lib)
        ctx.insert("pipe", "ingress/t",
                   key={"k": "v"}, action=("act", {"p": "v"}))
        mock_lib.p4tc_resp_handle.assert_not_called()
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
        mock_lib.p4tc_obj_create.assert_called_with(b"pipe", 2)
        ctx.destroy()

    def test_extern_update_calls_update(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.extern_update("pipe", "Counter", "ingress/bytes", key=1,
                          params={"packets": "100"})
        mock_lib.p4tc_update.assert_called_once()
        ctx.destroy()

    def test_extern_get_calls_resp_handle(self, mock_lib):
        ctx = Context(_lib=mock_lib)
        ctx.extern_get("pipe", "Counter", "ingress/bytes", key=1)
        mock_lib.p4tc_get.assert_called_once()
        mock_lib.p4tc_resp_handle.assert_called_once()
        ctx.destroy()

    def test_extern_get_returns_none(self, mock_lib):
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
