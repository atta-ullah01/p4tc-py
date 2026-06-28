"""Exception hierarchy for p4tc."""

import ctypes
import os


class P4TCError(Exception):
    """Base exception for all p4tc operations."""

    def __init__(self, message: str, errno: int | None = None):
        self.errno = errno
        if errno is not None:
            super().__init__(f"{message} (errno {errno}: {os.strerror(errno)})")
        else:
            super().__init__(message)


class ProvisionError(P4TCError):
    """Pipeline provisioning failed."""
    pass


class ContextError(P4TCError):
    """Failed to create or use a runtime context."""
    pass


class ObjectError(P4TCError):
    """Failed to construct a p4tc_obj."""
    pass


class KeyError_(P4TCError):
    """Failed to build a table key.

    Trailing underscore to avoid shadowing builtin KeyError.
    """
    pass


class EntryError(P4TCError):
    """Failed to allocate or configure a table entry."""
    pass


class CRUDError(P4TCError):
    """A create/update/get/delete operation failed."""
    pass


class SubscribeError(P4TCError):
    """A subscribe or unsubscribe operation failed."""
    pass


def _capture_errno() -> int:
    """Capture current C errno."""
    return ctypes.get_errno()
