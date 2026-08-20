# p4tc Python Bindings Usage Guide

This guide provides a comprehensive walkthrough of the Python bindings for the P4TC runtime API.

## 1. Setup

### Prerequisites
- A Linux kernel with P4TC support compiled and running.
- The `libp4tctrl.so` library installed and discoverable by the system (e.g., in `/usr/lib`).

### Installation
You can install the package via `pip`:
```bash
pip install .
```

### Provisioning the Pipeline
Before interacting with tables or externs, you must provision the pipeline into the kernel using the `provision` function. This requires root privileges or appropriate netlink capabilities.

```python
import p4tc

config = p4tc.provision("my_pipeline")
```
When finished, tear down the pipeline:
```python
config.destroy()
```

## 2. Context Lifecycle

The `Context` class acts as a handle to the Netlink transport for performing operations on the pipeline. The C library internally serializes operations, making `Context` thread-safe.

The best way to manage a `Context` is via a `with` block, ensuring resources are correctly freed.

```python
with p4tc.Context() as ctx:
    # Perform operations here
    pass
```

## 3. Table Operations

### Insert

```python
with p4tc.Context() as ctx:
    ctx.insert(
        "my_pipeline", "ingress/my_table",
        key=["10.0.0.1"],
        action=("ingress/send", ["eth0"])
    )
```

### Update

Updates modify existing entries. You must specify either the exact `key` or a `filter_str`.

```python
with p4tc.Context() as ctx:
    ctx.update(
        "my_pipeline", "ingress/my_table",
        key=["10.0.0.1"],
        action=("ingress/drop", [])
    )
```

### Delete

Delete an entry by key or use a filter string.

```python
with p4tc.Context() as ctx:
    ctx.delete("my_pipeline", "ingress/my_table", key=["10.0.0.1"])
```

### Get (Read Entries)

Table reads deliver results via a required callback. The callback receives
`(entries, phase)` where `entries` is a list of `TableEntry` objects.

When a pipeline schema is loaded (via `INTROSPECTION`), the key and action
params are automatically decoded into readable Python values:

```python
def on_get(entries, phase):
    for entry in entries:
        # entry.key is a dict of decoded field values
        print(f"Key: {entry.key}")           # {'dstAddr': '10.0.0.1'}
        print(f"Table: {entry.table_name}")  # 'ingress/nh_table'
        for act in entry.actions:
            print(f"Action: {act.name}")
            for name, p in act.params.items():
                print(f"  {name}: {p.decoded}")  # 2, '00:aa:bb:cc:dd:ee', ...

with p4tc.Context() as ctx:
    ctx.get("my_pipeline", "ingress/my_table",
            key=["10.0.0.1"], callback=on_get)
```

### Dump and Flush

- `dump(pipeline, table, callback=...)`: Reads all entries from a table (calls `get` without a key).
- `flush(pipeline, table)`: Deletes all entries from a table.

```python
with p4tc.Context() as ctx:
    # Dump all entries
    ctx.dump("my_pipeline", "ingress/my_table", callback=on_get)
    # Flush (delete all)
    ctx.flush("my_pipeline", "ingress/my_table")
```

## 4. Extern Operations

Externs are P4 stateful elements like Counters, Meters, or Registers.

### Update Extern

```python
with p4tc.Context() as ctx:
    # Update counter instance at index 1 (instance uses dotted path)
    ctx.extern_update("my_pipeline", "Counter", "ingress.my_counter", key=1, params=["1000", "2000"])
```
Note: `params` is a list of strings representing the parameter values.

### Get Extern

```python
def on_ext_get(entries, phase):
    for entry in entries:
        print(f"Extern: {entry.kind}, key={entry.key}")
        for name, p in entry.params.items():
            # p.decoded gives you the typed value
            print(f"  {name}: {p.decoded}")

with p4tc.Context() as ctx:
    ctx.extern_get("my_pipeline", "Counter", "ingress.my_counter",
                   key=1, callback=on_ext_get)
```
Note: `entry.params` is a `dict[str, Param]`. Each `Param` has `.decoded`
(typed Python value), `.display_value` (human-readable string), and `.value`
(raw `bytes` for advanced use).

## 5. Response Objects

### `TableEntry`

| Attribute | Type | Description |
|---|---|---|
| `table_name` | `str` | Full table path, e.g. `'ingress/nh_table'` |
| `key` | `dict[str, object]` | Decoded key fields — `{'dstAddr': '10.0.0.1'}` |
| `key_bytes` | `bytes` | Raw key bytes (advanced use) |
| `priority` | `int` | Entry priority |
| `actions` | `list[Action]` | List of actions on this entry |

### `Action`

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | Full action path, e.g. `'ingress/send_nh'` |
| `params` | `dict[str, Param]` | Keyed by param name |

### `Param`

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | Parameter name |
| `decoded` | `object` | Typed Python value — `int` for dev/bit, `str` for ipv4/ipv6/macaddr |
| `display_value` | `str` | `str(decoded)` — useful for printing |
| `value` | `bytes` | Raw bytes (advanced use) |
| `type_name` | `str \| None` | P4 type name from schema |

Type decoding is automatic when a schema is loaded:
- `ipv4` → `'10.0.0.1'`
- `ipv6` → `'::1'`
- `macaddr` → `'00:aa:bb:cc:dd:ee'`
- `dev` → `2` (ifindex as `int`)
- `bit<N>` / integers → `int`
- unknown → `bytes`

## 6. Callbacks and Phases

Callbacks receive results from the kernel. The signature is `def callback(entries, phase):`
where `entries` is a list of `TableEntry` or `ExternEntry` and `phase` is a `p4tc.Phase` enum.

The bindings internally filter phases — your callback is only invoked with actual data
(`Phase.SOT` or `Phase.MOT`). You do not need to check the phase or return a value.

This signature is consistent across all operations: `get`, `dump`, `extern_get`,
and `subscribe` all deliver `(entries, phase)`.

## 7. Subscriptions

Subscribe to real-time table events. Internally, `p4tc_subscribe()` registers
the subscription (returns a `sub_id`), and a background thread runs
`p4tc_subscribe_resp_handle()` where the C library handles events via epoll.

The callback signature matches `get`/`dump` — it receives a **list** of
`TableEntry` objects, not a single entry:

```python
import time

def on_event(entries, phase):
    for entry in entries:
        print(f"Update: key={entry.key}")

# Subscription requires a dedicated context — do not share with CRUD.
ctx_sub = p4tc.Context()
ctx_crud = p4tc.Context()

sub = ctx_sub.subscribe("my_pipeline", "ingress/my_table", callback=on_event)
sub.start()
print(sub.active)  # True

# Trigger events from the CRUD context
ctx_crud.insert("my_pipeline", "ingress/my_table",
                key=["10.0.0.1"], action=("ingress/drop", []))
time.sleep(1.0)

sub.stop()         # calls p4tc_unsubscribe, joins the thread
print(sub.active)  # False

ctx_crud.destroy()
ctx_sub.destroy()
```

> **Important**: Subscription and CRUD must use **separate** `Context` objects.
> A subscription socket enters a continuous listen state and cannot be used
> for outgoing commands at the same time.

An optional `filter_str` parameter can be passed to filter events:

```python
sub = ctx.subscribe("pipe", "ingress/t", callback=fn, filter_str="srcAddr=10.0.0.1")
```

## 8. Schema Validation

If a JSON schema is available (e.g. from the `p4c` compiler output), the Python
bindings can parse it at provision time and use it for two things:

1. **Input validation**: Dict-based `key` and action params are validated against
   the schema and serialized in the correct field order.
2. **Output decoding**: Response key bytes and action params are automatically
   decoded into typed Python values (`TableEntry.key`, `Param.decoded`).

Set the `INTROSPECTION` environment variable to the directory containing
`<pipeline>.json`:

```bash
export INTROSPECTION=/path/to/generated
```

With a schema loaded, you can use dicts for input:
```python
ctx.insert("my_pipeline", "ingress/my_table",
           key={"srcAddr": "192.168.1.1"},
           action=("ingress/send", {"port": "eth0"}))
```

And response entries will have decoded fields:
```python
def on_get(entries, phase):
    for e in entries:
        print(e.key)                    # {'srcAddr': '192.168.1.1'}
        for a in e.actions:
            for name, p in a.params.items():
                print(p.decoded)        # '00:aa:bb:cc:dd:ee', 2, ...
```

## 9. Error Handling

The package provides a hierarchy of exceptions under `P4TCError`, including:
- `ProvisionError`: Pipeline setup failed.
- `ContextError`: Context creation failed.
- `ObjectError`: Failed to allocate internal objects.
- `KeyError_`: Invalid key formulation.
- `EntryError`: Invalid action or parameters.
- `CRUDError`: The kernel rejected the operation (also raised on subscription failure).

Exceptions generally include an errno indicating why the operation failed in the kernel.

## 10. Notes

1. **Key Format**: A `key` parameter **must** be a list or a dict. Never pass a
   bare string. E.g. `key=["10.0.0.1"]` is correct; `key="10.0.0.1"` is wrong.
2. **Action Format**: Actions must be a tuple of `(action_path, parameters)`.
   E.g. `("ingress/drop", [])` or `("ingress/send", ["eth0"])`.
3. **Extern Params**: While input parameters for `extern_update` are a list of
   strings, the fetched `entry.params` is a `dict[str, Param]`.
   Use `p.decoded` or `.display_value` to read the values.
4. **Separate Contexts for Subscribe**: A subscription socket is in a continuous
   listen state — always use a dedicated `Context` for subscriptions and a
   separate `Context` for CRUD operations.
