"""Shared fixtures for the p4tc test suite."""

from unittest.mock import MagicMock

import pytest

from p4tc._ffi import ffi



SAMPLE_PIPELINE_JSON = {
    "tables": [{
        "name": "ingress/nh_table",
        "id": 1,
        "keysize": 32,
        "keyfields": [{
            "id": 1, "name": "srcAddr", "type": "ipv4",
            "match_type": "exact", "bitwidth": 32,
        }],
        "actions": [{
            "id": 1, "name": "ingress/send_nh",
            "params": [
                {"id": 1, "name": "port_id", "type": "dev", "bitwidth": 32},
                {"id": 2, "name": "dmac", "type": "macaddr", "bitwidth": 48},
                {"id": 3, "name": "smac", "type": "macaddr", "bitwidth": 48},
            ],
        }],
    }],
}



def _make_mock_lib(**overrides):
    """Return a MagicMock that satisfies Context.__init__.

    Every C function that the constructor or CRUD methods call is stubbed
    with a sane default.  Pass keyword arguments to override individual
    return values.
    """
    lib = MagicMock()

    defaults = {
        "p4tc_runt_ctx_create": ffi.cast("void *", 1),
        "p4tc_runt_ctx_destroy": None,
        "p4tc_runt_ctx_dflt_cb_set": None,
        "p4tc_obj_create": ffi.cast("void *", 10),
        "p4tc_obj_objname_set": 0,
        "p4tc_obj_destroy": None,
        "p4tc_make_key": ffi.cast("void *", 20),
        "p4tc_key_destroy": None,
        "p4tc_alloc_tbl_entry": ffi.cast("void *", 30),
        "p4tc_runt_tbl_attrs_prio_set": None,
        "p4tc_create_runt_act": ffi.cast("void *", 40),
        "p4tc_create_runt_ext": ffi.cast("void *", 50),
        "p4tc_create": 0,
        "p4tc_update": 0,
        "p4tc_get": 0,
        "p4tc_del": 0,
        "p4tc_resp_handle": 0,
        "p4tc_dump_handle": 0,
        "p4tc_subscribe": 1,  # return sub_id=1
        "p4tc_subscribe_resp_handle": 0,
        "p4tc_unsubscribe": 0,
    }
    defaults.update(overrides)

    for name, retval in defaults.items():
        getattr(lib, name).return_value = retval

    return lib


@pytest.fixture()
def mock_lib():
    """Pytest fixture wrapping _make_mock_lib()."""
    return _make_mock_lib()
