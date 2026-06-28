"""Tests for p4tc.types enums and p4tc.errors hierarchy."""

import pytest

from p4tc.types import Entity, MsgFlags, ObjType, Phase, Policy, Transport
from p4tc.errors import (
    P4TCError, ProvisionError, ContextError,
    ObjectError, KeyError_, EntryError, CRUDError, SubscribeError,
)




class TestTransport:
    def test_values(self):
        assert Transport.UNSPEC == 0
        assert Transport.NETLINK == 1


class TestObjType:
    def test_values(self):
        assert ObjType.UNSPEC == 0
        assert ObjType.TABLE == 1
        assert ObjType.EXTERN == 2


class TestEntity:
    def test_values(self):
        assert Entity.UNSPEC == 0
        assert Entity.KERNEL == 1
        assert Entity.TC == 2
        assert Entity.TIMER == 3


class TestPhase:
    def test_values(self):
        assert Phase.UNSPEC == 0
        assert Phase.SOT == 1
        assert Phase.MOT == 2
        assert Phase.EOT == 3
        assert Phase.ABT == 4


class TestMsgFlags:
    def test_values(self):
        assert MsgFlags.UNSPEC == 0
        assert MsgFlags.ROOT == 1
        assert MsgFlags.ACK == 2
        assert MsgFlags.ECHO == 4

    def test_bitwise_or(self):
        assert MsgFlags.ACK | MsgFlags.ECHO == 6


class TestPolicy:
    def test_values(self):
        assert Policy.UNSPEC == 0
        assert Policy.BASIC == 1




class TestErrors:
    def test_base_message(self):
        err = P4TCError("something went wrong")
        assert str(err) == "something went wrong"
        assert err.errno is None

    def test_errno_included_in_str(self):
        err = P4TCError("fail", errno=2)
        assert err.errno == 2
        assert "errno 2" in str(err)

    def test_all_subclasses_inherit_base(self):
        for cls in (ProvisionError, ContextError, ObjectError,
                    KeyError_, EntryError, CRUDError, SubscribeError):
            assert issubclass(cls, P4TCError)

    def test_crud_error_carries_errno(self):
        err = CRUDError("oops", errno=22)
        assert isinstance(err, P4TCError)
        assert err.errno == 22
