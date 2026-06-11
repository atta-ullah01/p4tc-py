"""Pipeline provisioning."""

from __future__ import annotations

from ._ffi import ffi, _require_lib
from .errors import ProvisionError, _capture_errno


class PipelineConfig:
    """Owns a provisioned pipeline config.

    Use as a context manager or call destroy() explicitly.
    Keep alive for the duration of CRUD operations.
    """

    def __init__(self, ptr, name: str) -> None:
        self._ptr = ptr
        self.name = name

    @property
    def is_valid(self) -> bool:
        return self._ptr is not None and self._ptr != ffi.NULL

    def destroy(self) -> None:
        """Free the underlying config. Safe to call multiple times."""
        if self._ptr is not None and self._ptr != ffi.NULL:
            lib = _require_lib()
            lib.p4tc_pipe_config_destroy(self._ptr)
            self._ptr = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.destroy()

    def __del__(self):
        self.destroy()

    def __repr__(self):
        state = "valid" if self.is_valid else "destroyed"
        return f"PipelineConfig({self.name!r}, {state})"


def provision(pipeline_name: str, template_path: str | None = None):
    """Load a P4TC pipeline into the kernel.

    Args:
        pipeline_name: e.g. "redirect_l2"
        template_path: directory with .template and .json files.
            Uses cwd if None.

    Returns:
        PipelineConfig — keep alive for CRUD.
    """
    lib = _require_lib()
    pname = pipeline_name.encode("utf-8")
    path = template_path.encode("utf-8") if template_path else ffi.NULL

    ptr = lib.p4tc_provision(pname, path)
    if ptr == ffi.NULL:
        raise ProvisionError(
            f"Failed to provision '{pipeline_name}'",
            errno=_capture_errno() or None,
        )

    return PipelineConfig(ptr, pipeline_name)
