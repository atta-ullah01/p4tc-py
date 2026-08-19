#!/usr/bin/env python3
"""Example: event subscription.

Uses a separate context for CRUD while subscription is active.

Pipeline setup (inside the P4TC VM):
    tar xzf examples/register.tgz -C ~
    cd ~/register
    sudo tc p4template del pipeline/register 2>/dev/null; true
    sudo tc p4template del extern/root/Register 2>/dev/null; true
    sudo INTROSPECTION=./generated bash generated/register.template

Run (see README.md for install prerequisites):
    cd /path/to/p4tc_py
    sudo INTROSPECTION=~/register/generated .venv/bin/python examples/subscribe.py
"""

import time
import p4tc

PIPE = "register"
TABLE = "ingress/nh_table"

event_count = 0


def on_event(entries, phase):
    """Subscription callback, receives ([TableEntry, ...], Phase), same as get/dump."""
    global event_count
    event_count += len(entries)
    for entry in entries:
        print(f"  event: phase={phase.name}, table={entry.table_name}, "
              f"key={entry.key}")


def main():
    config = p4tc.provision(PIPE)

    # Subscription and CRUD need separate contexts.
    ctx_sub = p4tc.Context()
    ctx_crud = p4tc.Context()

    print("subscribe ...")
    sub = ctx_sub.subscribe(PIPE, TABLE, callback=on_event)
    sub.start()
    print(f"  active={sub.active}")

    # Trigger some events (on a different context)
    print("insert (triggers event) ...")
    ctx_crud.insert(
        PIPE, TABLE,
        key=["10.0.0.1"],
        action=("ingress/drop", []),
    )

    print("delete (triggers event) ...")
    ctx_crud.delete(PIPE, TABLE, key=["10.0.0.1"])

    # Give the background thread time to receive events
    time.sleep(1.0)

    # Stop
    print("stop ...")
    sub.stop()
    print(f"  active={sub.active}")
    print(f"  total events: {event_count}")

    ctx_crud.destroy()
    ctx_sub.destroy()
    config.destroy()
    print("\ndone.")


if __name__ == "__main__":
    main()
