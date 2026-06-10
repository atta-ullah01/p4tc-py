"""Loads libp4tctrl.so via cffi ABI mode.

Attempts dlopen at import time. If it fails, the error is stored
and re-raised on first actual use via _require_lib().
"""
import os
import cffi
from ._cdefs import CDEFS

ffi = cffi.FFI()
ffi.cdef(CDEFS)

_lib = None
_load_error = None

try:
    _lib_path = os.environ.get("P4TC_LIB_PATH", "libp4tctrl.so")
    _lib = ffi.dlopen(_lib_path)
except OSError as e:
    _load_error = OSError(
        f"Could not load '{_lib_path}'. "
        f"Set P4TC_LIB_PATH or install the p4tc-ctrl-runt-api package."
    )
    _load_error.__cause__ = e

def _require_lib():
    """Return the loaded library, or raise if unavailable."""
    if _lib is None:
        raise _load_error
    return _lib

lib = _lib
