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

Table reads deliver results via a required callback. The callback receives a list of entries and is only called when there are results (phase filtering is handled internally).

```python
def on_get(entries, phase):
    for entry in entries:
        print(f"Key: {entry.key_bytes.hex()}, Actions: {len(entry.actions)}")
        for act in entry.actions:
            for p in act.params.values():
                print(f"  {p.name}: {p.value.hex()}")

with p4tc.Context() as ctx:
    ctx.get("my_pipeline", "ingress/my_table", callback=on_get)
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
        for name, param in entry.params.items():
            print(f"  {name}: {param.value.hex()}")

with p4tc.Context() as ctx:
    ctx.extern_get("my_pipeline", "Counter", "ingress.my_counter", key=1, callback=on_ext_get)
```
Note: `entry.params` is a `dict[str, Param]`. Each `Param` has `name`, `value` (raw `bytes`), `size`, and `type_name`.

## 5. Callbacks and Phases

Callbacks receive results from the kernel. The signature is `def callback(entries, phase):`
where `entries` is a list of `TableEntry` or `ExternEntry` and `phase` is a `p4tc.Phase` enum.

The bindings internally filter phases — your callback is only invoked with actual data
(`Phase.SOT` or `Phase.MOT`). You do not need to check the phase or return a value.

## 6. Subscriptions

Subscribe to real-time table events. Internally, `p4tc_subscribe()` registers
the subscription (returns a `sub_id`), and a background thread runs
`p4tc_subscribe_resp_handle()` where the C library handles events via epoll.

```python
import time

def on_event(entry, phase):
    print(f"Update: {entry}")

with p4tc.Context() as ctx:
    with ctx.subscribe("my_pipeline", "ingress/my_table", callback=on_event) as sub:
        print(f"active={sub.active}")
        time.sleep(60)
    # sub.stop() is called automatically on exit — invokes p4tc_unsubscribe
# ctx.destroy() is called automatically — stops all remaining subscriptions first
```

You can also manage the lifecycle manually:

```python
ctx = p4tc.Context()
sub = ctx.subscribe("my_pipeline", "ingress/my_table", callback=on_event)
sub.start()
print(sub.active)  # True
# ... do work ...
sub.stop()         # calls p4tc_unsubscribe, joins the thread
print(sub.active)  # False
ctx.destroy()
```

An optional `filter_str` parameter can be passed to filter events:

```python
sub = ctx.subscribe("pipe", "ingress/t", callback=fn, filter_str="srcAddr=10.0.0.1")
```

## 7. Schema Validation

If a JSON schema is available (e.g. from the `p4c` compiler output), the Python bindings can parse it and automatically validate dict-based inputs.

Set the `INTROSPECTION` environment variable to the directory containing `<pipeline>.json`:

```bash
export INTROSPECTION=/path/to/my_pipeline
```

Then, you can use dictionaries instead of lists for `key` and `action` parameters:
```python
ctx.insert("my_pipeline", "ingress/my_table",
           key={"srcAddr": "192.168.1.1"},
           action=("ingress/send", {"port": "eth0"}))
```
The bindings will guarantee the keys and action parameters are serialized in the correct order for the C runtime API.

## 8. Error Handling

The package provides a hierarchy of exceptions under `P4TCError`, including:
- `ProvisionError`: Pipeline setup failed.
- `ContextError`: Context creation failed.
- `ObjectError`: Failed to allocate internal objects.
- `KeyError_`: Invalid key formulation.
- `EntryError`: Invalid action or parameters.
- `CRUDError`: The kernel rejected the operation (also raised on subscription failure).

Exceptions generally include an errno indicating why the operation failed in the kernel.

## 9. Common Gotchas

1. **Key Format**: A `key` parameter **must** be a list or a dict. Never pass a bare string. E.g. `key=["10.0.0.1"]` is correct. `key="10.0.0.1"` is wrong, as Python will iterate over the string characters.
2. **Action Format**: Actions must be a tuple of `(action_path, parameters)`. E.g. `("ingress/drop", [])` or `("ingress/send", ["eth0"])`.
3. **Extern Params**: While input parameters for `extern_update` are a list of strings, the fetched `entry.params` is a `dict[str, Param]`. Use `.values()` to iterate over them.
