"""JSON introspection schema for P4TC pipelines.

Parses the <pipeline>.json file from p4c to extract table
structure. Used to validate dict keys and action params.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParamSchema:
    """A single action parameter."""
    id: int
    name: str
    type: str
    bitwidth: int


@dataclass(frozen=True)
class ActionSchema:
    """A table action with its parameters."""
    id: int
    name: str
    params: tuple[ParamSchema, ...]

    def validate_params(self, params: dict[str, str]) -> list[str]:
        """Check param names, return values in schema order."""
        schema_names = {p.name for p in self.params}
        unknown = set(params.keys()) - schema_names
        if unknown:
            raise ValueError(
                f"Unknown param(s) {unknown} for action '{self.name}'. "
                f"Available: {sorted(schema_names)}"
            )
        return [params[p.name] for p in self.params if p.name in params]


@dataclass(frozen=True)
class KeyFieldSchema:
    """A single key field in a table."""
    id: int
    name: str
    type: str
    match_type: str
    bitwidth: int


@dataclass(frozen=True)
class TableSchema:
    """Schema for a P4TC table."""
    name: str
    id: int
    keysize: int
    key_fields: tuple[KeyFieldSchema, ...]
    actions: dict[str, ActionSchema]

    def validate_key(self, key: dict[str, str]) -> list[str]:
        """Check field names, return values in schema order."""
        schema_names = {f.name for f in self.key_fields}
        unknown = set(key.keys()) - schema_names
        if unknown:
            raise ValueError(
                f"Unknown key field(s) {unknown}. "
                f"Available: {sorted(schema_names)}"
            )
        return [key[f.name] for f in self.key_fields if f.name in key]

    def get_action(self, action_path: str):
        return self.actions.get(action_path)


@dataclass
class PipelineSchema:
    """Full schema for a provisioned pipeline."""
    name: str
    tables: dict[str, TableSchema]

    def get_table(self, table_path: str):
        return self.tables.get(table_path)


# module-level registry, populated by provision()
_registry: dict[str, PipelineSchema] = {}


def _get_schema(pipeline_name: str):
    return _registry.get(pipeline_name)


def _register_schema(schema: PipelineSchema):
    _registry[schema.name] = schema


def _unregister_schema(pipeline_name: str):
    _registry.pop(pipeline_name, None)


def load_pipeline_schema(pipeline_name, template_path=None):
    """Parse the pipeline JSON file.

    Returns PipelineSchema or None if the file doesn't exist.
    """
    if template_path:
        json_path = Path(template_path) / f"{pipeline_name}.json"
    else:
        json_path = Path(f"{pipeline_name}.json")

    if not json_path.exists():
        return None

    with open(json_path) as f:
        data = json.load(f)

    tables = {}
    for tbl in data.get("tables", []):
        key_fields = tuple(
            KeyFieldSchema(
                id=kf["id"], name=kf["name"], type=kf["type"],
                match_type=kf.get("match_type", "exact"),
                bitwidth=kf["bitwidth"],
            )
            for kf in tbl.get("keyfields", [])
        )
        actions = {}
        for act in tbl.get("actions", []):
            params = tuple(
                ParamSchema(
                    id=p["id"], name=p["name"],
                    type=p["type"], bitwidth=p["bitwidth"],
                )
                for p in act.get("params", [])
            )
            actions[act["name"]] = ActionSchema(
                id=act["id"], name=act["name"], params=params,
            )
        tables[tbl["name"]] = TableSchema(
            name=tbl["name"], id=tbl["id"],
            keysize=tbl.get("keysize", 0),
            key_fields=key_fields, actions=actions,
        )

    return PipelineSchema(name=pipeline_name, tables=tables)
