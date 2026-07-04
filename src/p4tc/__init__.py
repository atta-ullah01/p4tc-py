"""p4tc — Python bindings for the P4TC runtime C API.

Quick start::

    import p4tc

    config = p4tc.provision("redirect_l2")
    with p4tc.Context() as ctx:
        ctx.insert("redirect_l2", "ingress/nh_table",
                   key={"srcAddr": "192.168.1.10"},
                   action=("ingress/send_nh", {
                       "port_id": "port0",
                       "dmac": "00:AA:BB:CC:DD:EE",
                       "smac": "00:11:22:33:44:55",
                   }))
    config.destroy()
"""

__version__ = "0.1.0"

from ._schema import PipelineSchema
from .context import Context, Subscription
from .entry import Action, Param, TableEntry
from .errors import (
    CRUDError, ContextError, EntryError, KeyError_,
    ObjectError, P4TCError, ProvisionError, SubscribeError,
)
from .provision import PipelineConfig, provision
from .types import Entity, MsgFlags, ObjType, Phase, Policy, Transport

__all__ = [
    "provision", "Context", "Subscription", "PipelineConfig", "PipelineSchema",
    "TableEntry", "Action", "Param",
    "Transport", "ObjType", "Entity", "Phase", "MsgFlags", "Policy",
    "P4TCError", "ProvisionError", "ContextError",
    "ObjectError", "KeyError_", "EntryError", "CRUDError", "SubscribeError",
]
