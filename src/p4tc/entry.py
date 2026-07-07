"""Structured response types for table and extern entries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:

    name: str
    value: bytes
    size: int
    type_name: str | None = None

    def __repr__(self):
        val_hex = self.value.hex() if len(self.value) <= 16 else \
            self.value[:16].hex() + "..."
        return (f"Param({self.name!r}, {val_hex}, "
                f"size={self.size}, type={self.type_name!r})")


@dataclass(frozen=True)
class Action:

    name: str
    index: int
    params: dict[str, Param] = field(default_factory=dict)

    def __repr__(self):
        param_names = list(self.params.keys())
        return f"Action({self.name!r}, index={self.index}, params={param_names})"


@dataclass(frozen=True)
class TableEntry:

    table_name: str | None
    priority: int
    key_bytes: bytes
    key_size: int
    mask_bytes: bytes | None = None
    permissions: int = 0
    dynamic: bool = False
    aging: int = 0
    actions: list[Action] = field(default_factory=list)

    def __repr__(self):
        act_names = [a.name for a in self.actions]
        return (f"TableEntry({self.table_name!r}, prio={self.priority}, "
                f"key={self.key_bytes.hex()}, actions={act_names})")


@dataclass(frozen=True)
class ExternEntry:

    kind: str | None
    instance: str | None
    key: int
    ext_id: int = 0
    inst_id: int = 0
    params: dict[str, Param] = field(default_factory=dict)

    def __repr__(self):
        param_names = list(self.params.keys())
        return (f"ExternEntry({self.kind!r}/{self.instance!r}, "
                f"key={self.key}, params={param_names})")
