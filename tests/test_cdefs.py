"""Tests for _cdefs declarations and the FFI library loader."""

import pytest

from p4tc._cdefs import CDEFS


class TestCdefs:
    """Verify the CDEFS string contains the expected API surface."""

    def test_is_nonempty_string(self):
        assert isinstance(CDEFS, str)
        assert len(CDEFS) > 1000

    def test_contains_core_functions(self):
        for fn in ("p4tc_provision", "p4tc_runt_ctx_create",
                    "p4tc_obj_create", "p4tc_make_key",
                    "p4tc_alloc_tbl_entry", "p4tc_create_runt_act",
                    "p4tc_create", "p4tc_update", "p4tc_get", "p4tc_del",
                    "p4tc_resp_handle", "p4tc_subscribe"):
            assert fn in CDEFS, f"{fn} missing from CDEFS"

    def test_uses_new_string_array_signatures(self):
        # post-e0ff928: _Generic macros replaced with (int n, const char**)
        assert "int n_kfs" in CDEFS
        assert "const char **kfs" in CDEFS
        assert "int n_params" in CDEFS
        assert "const char **params" in CDEFS

    def test_has_extern_api(self):
        assert "p4tc_create_runt_ext" in CDEFS

    def test_parseable_by_cffi(self):
        import cffi
        test_ffi = cffi.FFI()
        test_ffi.cdef(CDEFS)  # raises on syntax error


class TestFFILoader:
    """Verify the deferred library loader works outside the VM."""

    def _skip_if_loaded(self):
        from p4tc._ffi import _lib
        if _lib is not None:
            pytest.skip("libp4tctrl.so loaded — running inside the VM?")

    def test_require_lib_gives_helpful_error(self):
        self._skip_if_loaded()
        from p4tc._ffi import _require_lib
        with pytest.raises(OSError, match="P4TC_LIB_PATH"):
            _require_lib()

    def test_lib_is_none_outside_vm(self):
        self._skip_if_loaded()
        from p4tc._ffi import lib
        assert lib is None

    def test_load_error_is_stored(self):
        self._skip_if_loaded()
        from p4tc._ffi import _load_error
        assert isinstance(_load_error, OSError)
