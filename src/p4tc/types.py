"""Enums and constants from the C API.

Values from p4tc_runtime_api.h and linux/p4tc.h.
"""

import enum


class Transport(enum.IntEnum):
    """TML operation types."""
    UNSPEC  = 0
    NETLINK = 1  # P4TC_TML_OPS_NL


class ObjType(enum.IntEnum):
    """Runtime object types for p4tc_obj_create()."""
    UNSPEC = 0
    TABLE  = 1  # P4TC_OBJ_RUNTIME_TABLE
    EXTERN = 2  # P4TC_OBJ_RUNTIME_EXTERN


class Entity(enum.IntEnum):
    """Who created the entry."""
    UNSPEC = 0
    KERNEL = 1  # P4TC_ENTITY_KERNEL
    TC     = 2  # P4TC_ENTITY_TC
    TIMER  = 3  # P4TC_ENTITY_TIMER


class Phase(enum.IntEnum):
    """Transaction phase in callbacks."""
    UNSPEC = 0
    SOT    = 1  # start of transaction
    MOT    = 2  # middle
    EOT    = 3  # end (done, obj is NULL)
    ABT    = 4  # abort


class MsgFlags(enum.IntFlag):
    """Message control flags for CRUD ops."""
    UNSPEC = 0
    ROOT   = 1  # dump/flush entire table
    ACK    = 2  # request kernel ack
    ECHO   = 4  # request echo


class Policy(enum.IntEnum):
    """Context socket policy."""
    UNSPEC = 0
    BASIC  = 1  # one CRUD socket + one subscription socket
