#!/usr/bin/env python3
"""Example: event subscription.

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

    with p4tc.Context() as ctx:
        print("subscribe ...")
        sub = ctx.subscribe(PIPE, TABLE, callback=on_event)
        sub.start()
        print(f"  active={sub.active}")

        print("insert (triggers event) ...")
        ctx.insert(
            PIPE, TABLE,
            key=["10.0.0.1"],
            action=("ingress/drop", []),
        )

        print("delete (triggers event) ...")
        ctx.delete(PIPE, TABLE, key=["10.0.0.1"])

        time.sleep(1.0)

        print("stop ...")
        sub.stop()
        print(f"  active={sub.active}")
        print(f"  total events: {event_count}")

    config.destroy()
    print("\ndone.")


if __name__ == "__main__":
    main()
