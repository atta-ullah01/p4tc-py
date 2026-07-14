"""Tests for the JSON introspection schema parser and validation."""

import json

import pytest

from p4tc._schema import (
    ActionSchema, ExternInstanceSchema, ExternSchema,
    KeyFieldSchema, ParamSchema,
    PipelineSchema, TableSchema, load_pipeline_schema,
)


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
    "externs": [{
        "name": "Register",
        "id": "0x1",
        "instances": [{
            "inst_name": "ingress.reg1",
            "inst_id": 1,
            "params": [
                {"id": 1, "name": "index", "type": "bit32",
                 "attr": "tc_key", "bitwidth": 32},
                {"id": 2, "name": "protocol", "type": "bit8",
                 "attr": "param", "bitwidth": 8},
                {"id": 3, "name": "aux", "type": "bit8",
                 "attr": "param", "bitwidth": 8},
            ],
        }],
    }],
}


def _build_schema():
    """Construct a PipelineSchema from the sample JSON fixture."""
    tables = {}
    for tbl in SAMPLE_PIPELINE_JSON["tables"]:
        key_fields = tuple(
            KeyFieldSchema(
                id=k["id"], name=k["name"], type=k["type"],
                match_type=k.get("match_type", "exact"),
                bitwidth=k["bitwidth"],
            )
            for k in tbl["keyfields"]
        )
        actions = {}
        for a in tbl["actions"]:
            params = tuple(
                ParamSchema(id=p["id"], name=p["name"],
                            type=p["type"], bitwidth=p["bitwidth"])
                for p in a["params"]
            )
            actions[a["name"]] = ActionSchema(
                id=a["id"], name=a["name"], params=params,
            )
        tables[tbl["name"]] = TableSchema(
            name=tbl["name"], id=tbl["id"],
            keysize=tbl.get("keysize", 0),
            key_fields=key_fields, actions=actions,
        )
    return PipelineSchema(name="test_pipe", tables=tables, externs={})


class TestPipelineSchema:
    def test_parse_creates_pipeline(self):
        s = _build_schema()
        assert s.name == "test_pipe"
        assert "ingress/nh_table" in s.tables

    def test_table_metadata(self):
        t = _build_schema().get_table("ingress/nh_table")
        assert t.id == 1
        assert t.keysize == 32
        assert len(t.key_fields) == 1
        assert t.key_fields[0].name == "srcAddr"

    def test_nonexistent_table_returns_none(self):
        assert _build_schema().get_table("does_not_exist") is None

    def test_nonexistent_action_returns_none(self):
        t = _build_schema().get_table("ingress/nh_table")
        assert t.get_action("does_not_exist") is None


class TestKeyValidation:
    def test_known_field_passes(self):
        t = _build_schema().get_table("ingress/nh_table")
        assert t.validate_key({"srcAddr": "10.0.0.1"}) == ["10.0.0.1"]

    def test_unknown_field_raises(self):
        t = _build_schema().get_table("ingress/nh_table")
        with pytest.raises(ValueError, match="Unknown key field"):
            t.validate_key({"badField": "1.2.3.4"})


class TestParamValidation:
    def test_all_params_pass(self):
        a = (_build_schema().get_table("ingress/nh_table")
                            .get_action("ingress/send_nh"))
        result = a.validate_params({
            "port_id": "p0",
            "dmac": "aa:bb:cc:dd:ee:ff",
            "smac": "11:22:33:44:55:66",
        })
        assert result == ["p0", "aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"]

    def test_unknown_param_raises(self):
        a = (_build_schema().get_table("ingress/nh_table")
                            .get_action("ingress/send_nh"))
        with pytest.raises(ValueError, match="Unknown param"):
            a.validate_params({"nope": "val"})

    def test_params_reordered_to_schema_order(self):
        a = (_build_schema().get_table("ingress/nh_table")
                            .get_action("ingress/send_nh"))
        result = a.validate_params({
            "smac": "s", "port_id": "p", "dmac": "d",
        })
        assert result == ["p", "d", "s"]

    def test_partial_params_accepted(self):
        a = (_build_schema().get_table("ingress/nh_table")
                            .get_action("ingress/send_nh"))
        assert a.validate_params({"port_id": "p0"}) == ["p0"]


class TestSchemaFileLoading:
    def test_loads_from_json_file(self, tmp_path):
        (tmp_path / "test_pipe.json").write_text(
            json.dumps(SAMPLE_PIPELINE_JSON))
        s = load_pipeline_schema("test_pipe", str(tmp_path))
        assert s is not None
        assert "ingress/nh_table" in s.tables

    def test_missing_file_returns_none(self, tmp_path):
        assert load_pipeline_schema("nope", str(tmp_path)) is None

    def test_loads_via_introspection_env(self, tmp_path, monkeypatch):
        (tmp_path / "test_pipe.json").write_text(
            json.dumps(SAMPLE_PIPELINE_JSON))
        monkeypatch.setenv("INTROSPECTION", str(tmp_path))
        s = load_pipeline_schema("test_pipe")
        assert s is not None
        assert "Register" in s.externs


class TestExternSchema:
    def test_extern_parsed_from_json(self, tmp_path):
        (tmp_path / "test_pipe.json").write_text(
            json.dumps(SAMPLE_PIPELINE_JSON))
        s = load_pipeline_schema("test_pipe", str(tmp_path))
        assert "Register" in s.externs
        ext = s.get_extern("Register")
        assert ext.id == "0x1"

    def test_instance_lookup(self, tmp_path):
        (tmp_path / "test_pipe.json").write_text(
            json.dumps(SAMPLE_PIPELINE_JSON))
        s = load_pipeline_schema("test_pipe", str(tmp_path))
        inst = s.get_extern("Register").get_instance("ingress.reg1")
        assert inst is not None
        assert inst.id == 1

    def test_param_names_exclude_keys(self, tmp_path):
        (tmp_path / "test_pipe.json").write_text(
            json.dumps(SAMPLE_PIPELINE_JSON))
        s = load_pipeline_schema("test_pipe", str(tmp_path))
        inst = s.get_extern("Register").get_instance("ingress.reg1")
        assert inst.param_names == ("protocol", "aux")
        assert "index" not in inst.param_names

    def test_nonexistent_extern_returns_none(self, tmp_path):
        (tmp_path / "test_pipe.json").write_text(
            json.dumps(SAMPLE_PIPELINE_JSON))
        s = load_pipeline_schema("test_pipe", str(tmp_path))
        assert s.get_extern("NoSuchExtern") is None

    def test_nonexistent_instance_returns_none(self, tmp_path):
        (tmp_path / "test_pipe.json").write_text(
            json.dumps(SAMPLE_PIPELINE_JSON))
        s = load_pipeline_schema("test_pipe", str(tmp_path))
        assert s.get_extern("Register").get_instance("no.inst") is None

    def test_pipeline_without_externs(self):
        s = PipelineSchema(name="bare", tables={}, externs={})
        assert s.get_extern("Register") is None
