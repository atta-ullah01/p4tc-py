#!/usr/bin/env python3
"""Example: extern update and get.

Externs only support update and get — no insert or delete.

Pipeline setup (inside the P4TC VM):
    tar xzf examples/register.tgz -C ~
    cd ~/register
    sudo tc p4template del pipeline/register 2>/dev/null; true
    sudo tc p4template del extern/root/Register 2>/dev/null; true
    sudo INTROSPECTION=./generated bash generated/register.template

Run (see README.md for install prerequisites):
    cd /path/to/p4tc_py
    sudo INTROSPECTION=~/register/generated .venv/bin/python examples/extern_ops.py
"""

import p4tc

PIPE = "register"


def on_extern_get(entries, phase):
    """Callback for extern_get — receives ([ExternEntry, ...], Phase)."""
    print(f"  phase={phase.name}, {len(entries)} entries")
    for e in entries:
        print(f"  kind={e.kind}, instance={e.instance}, key={e.key}")
        for name, p in e.params.items():
            print(f"    {name}: {p.display_value}")


def main():
    config = p4tc.provision(PIPE)

    with p4tc.Context() as ctx:
        # Update extern register at index 1
        print("extern_update ...")
        ctx.extern_update(PIPE, "Register", "ingress.reg1",
                          key=1, params=["42", "99"])
        print("  OK")

        # Read it back (callback-driven)
        print("extern_get ...")
        ctx.extern_get(PIPE, "Register", "ingress.reg1",
                       key=1, callback=on_extern_get)

    config.destroy()
    print("\ndone.")


if __name__ == "__main__":
    main()
