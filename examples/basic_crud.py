#!/usr/bin/env python3
"""Example: basic table CRUD (insert, get, update, delete, dump, flush).

Pipeline setup (inside the P4TC VM):
    tar xzf examples/register.tgz -C ~
    cd ~/register
    sudo tc p4template del pipeline/register 2>/dev/null; true
    sudo tc p4template del extern/root/Register 2>/dev/null; true
    sudo INTROSPECTION=./generated bash generated/register.template

Run (see README.md for install prerequisites):
    cd /path/to/p4tc_py
    sudo INTROSPECTION=~/register/generated .venv/bin/python examples/basic_crud.py
"""

import p4tc

PIPE = "register"
TABLE = "ingress/nh_table"


def on_get(entries, phase):
    """Callback for get/dump — receives ([TableEntry, ...], Phase)."""
    print(f"  phase={phase.name}, {len(entries)} entries")
    for e in entries:
        print(f"  table={e.table_name}, key={e.key_bytes.hex()}, prio={e.priority}")
        for a in e.actions:
            print(f"    action={a.name}")
            for name, p in a.params.items():
                print(f"      {name}: {p.display_value}")


def main():
    # provision() returns a PipelineConfig — keep it alive for the
    # duration of the program, otherwise GC destroys the pipeline.
    config = p4tc.provision(PIPE)

    with p4tc.Context() as ctx:
        # Insert
        print("insert ...")
        ctx.insert(
            PIPE, TABLE,
            key=["10.0.0.1"],
            action=("ingress/send_nh", ["eth0", "00:aa:bb:cc:dd:ee", "00:11:22:33:44:55"]),
        )
        print("  OK")

        # Get (single entry by key, callback-driven)
        print("get ...")
        ctx.get(PIPE, TABLE, key=["10.0.0.1"], callback=on_get)

        # Update (change action to drop)
        print("update ...")
        ctx.update(PIPE, TABLE, key=["10.0.0.1"], action=("ingress/drop", []))
        print("  OK")

        # Delete
        print("delete ...")
        ctx.delete(PIPE, TABLE, key=["10.0.0.1"])
        print("  OK")

        # Insert two entries, dump all, then flush
        print("insert two entries ...")
        for ip in ["10.0.0.1", "10.0.0.2"]:
            ctx.insert(
                PIPE, TABLE,
                key=[ip],
                action=("ingress/send_nh", ["eth0", "00:aa:bb:cc:dd:ee", "00:11:22:33:44:55"]),
            )
        print("  OK")

        print("dump ...")
        ctx.dump(PIPE, TABLE, callback=on_get)

        print("flush ...")
        ctx.flush(PIPE, TABLE)
        print("  OK")

    config.destroy()
    print("\ndone.")


if __name__ == "__main__":
    main()
