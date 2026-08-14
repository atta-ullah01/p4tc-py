# p4tc Python Bindings

Python bindings for the P4TC runtime C API via cffi.

## Installation

```bash
pip install .
# or for development:
pip install ".[dev]"
```

**Requirements**: Linux kernel with P4TC support and `libp4tctrl.so` installed.

> If developing inside a VirtualBox VM (e.g. via Vagrant), create your Python
> venv on the local filesystem (`~` or `/tmp`), not on `/vagrant`.

## Quick Start

```python
import p4tc

# 1. Provision the pipeline into the kernel
config = p4tc.provision("my_pipeline")

with p4tc.Context() as ctx:
    # 2. Insert a table entry
    ctx.insert("my_pipeline", "ingress/my_table",
               key=["10.0.0.1"],
               action=("ingress/send", ["eth0"]))

    # 3. Read entries (callback is required)
    def on_get(entries, phase):
        for e in entries:
            print(e)

    ctx.get("my_pipeline", "ingress/my_table", callback=on_get)

    # 4. Delete
    ctx.delete("my_pipeline", "ingress/my_table", key=["10.0.0.1"])

config.destroy()
```

With a JSON schema (from `p4c`), use dicts for validated key/param ordering:

```python
import os
os.environ["INTROSPECTION"] = "./generated"

config = p4tc.provision("my_pipeline")
with p4tc.Context() as ctx:
    ctx.insert("my_pipeline", "ingress/my_table",
               key={"srcAddr": "192.168.1.1"},
               action=("ingress/send", {"port": "eth0"}))
```

See [docs/usage.md](docs/usage.md) for the full API reference covering
update, dump, flush, externs, subscriptions, error handling, and callbacks.


