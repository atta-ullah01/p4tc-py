"""Structured response types for table and extern entries."""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:

    name: str
    value: bytes
    size: int
    type_name: str | None = None

    @property
    def decoded(self) -> object:
        """Return the param value as a typed Python object.

        - dev      -> int  (ifindex, little-endian u32)
        - ipv4     -> str  (dotted notation, e.g. '10.0.0.1')
        - ipv6     -> str  (colon notation)
        - macaddr  -> str  (colon-hex, e.g. '00:aa:bb:cc:dd:ee')
        - anything else -> bytes (raw)
        """
        t = (self.type_name or "").lower()
        try:
            if t == "dev":
                return struct.unpack_from("<I", self.value.ljust(4, b"\x00"))[0]
            if t == "ipv4":
                return socket.inet_ntop(socket.AF_INET, self.value[:4])
            if t == "ipv6":
                return socket.inet_ntop(socket.AF_INET6, self.value[:16])
            if t == "macaddr":
                return ":".join(f"{b:02x}" for b in self.value[:6])
        except Exception:
            pass
        return self.value

    @property
    def display_value(self) -> str:
        """String representation of the decoded value (backwards compat)."""
        d = self.decoded
        if isinstance(d, bytes):
            return d.hex()
        return str(d)

    def __repr__(self):
        return (f"Param({self.name!r}, {self.display_value}, "
                f"size={self.size}, type={self.type_name!r})")


@dataclass(frozen=True)
class Action:

    name: str
    index: int
    params: dict[str, Param] = field(default_factory=dict)

    def __repr__(self):
        if self.params:
            param_str = ", ".join(
                f"{n}={p.display_value}" for n, p in self.params.items()
            )
            return f"Action({self.name!r}, index={self.index}, {param_str})"
        return f"Action({self.name!r}, index={self.index})"


@dataclass(frozen=True)
class TableEntry:

    table_name: str | None
    priority: int
    key_bytes: bytes
    key_size: int
    key: dict[str, object] = field(default_factory=dict)
    mask_bytes: bytes | None = None
    permissions: int = 0
    dynamic: bool = False
    aging: int = 0
    actions: list[Action] = field(default_factory=list)

    def __repr__(self):
        key_str = (
            repr(self.key) if self.key
            else self.key_bytes.hex()
        )
        act_reprs = [repr(a) for a in self.actions]
        return (f"TableEntry({self.table_name!r}, prio={self.priority}, "
                f"key={key_str}, actions={act_reprs})")


@dataclass(frozen=True)
class ExternEntry:

    kind: str | None
    instance: str | None
    key: int
    ext_id: int = 0
    inst_id: int = 0
    params: dict[str, Param] = field(default_factory=dict)

    def __repr__(self):
        if self.params:
            param_str = ", ".join(
                f"{n}={p.display_value}" for n, p in self.params.items()
            )
            return (f"ExternEntry({self.kind!r}/{self.instance!r}, "
                    f"key={self.key}, {param_str})")
        return (f"ExternEntry({self.kind!r}/{self.instance!r}, "
                f"key={self.key})")
