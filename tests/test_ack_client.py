"""Tests for the verified-write client behaviour (robust ack functionality).

Target contract (TDD):
- write_params() on RW params sends FUNC 0x03 and returns the applied values
  from the echo ack (live-proven: echo == applied state, including clamping).
- Idempotent writes retry up to 3 attempts on timeout; exhaustion raises
  VentoAckError reporting the attempt count.
- Invert-value writes (value 2 on params whose datasheet defines "2 - Invert",
  e.g. POWER) never retry: a lost ack after an applied toggle would double-apply.
- W-only params (FILTER_RESET etc.) are routed to fire-and-forget FUNC 0x02 and
  return an empty mapping (unverifiable by design).
- Mixed RW + W-only writes are rejected before any traffic.
- Writes of read-only params are rejected before any traffic.
- Negative acks raise VentoUnsupportedParamError carrying the applied subset.
- Acks from the wrong device raise VentoAckMismatchError without retry.
- Schedule writes accept the write-only day selectors (0, 8, 9); schedule reads
  reject them (read selector range is 1-7 only).
"""

import pytest
from blauberg_vento.client import AsyncVentoClient, VentoClient
from blauberg_vento.exceptions import (
    VentoAckError,
    VentoAckMismatchError,
    VentoCapabilityError,
    VentoTimeoutError,
    VentoUnsupportedParamError,
    VentoValueError,
)
from blauberg_vento.parameters import Func, Param
from blauberg_vento.protocol import build_packet

DEV_ID = "002D003957425711"
OTHER_ID = "1122334455667788"
PWD = "1111"
HOST = "192.0.2.10"


def _ack(data: bytes, device_id: str = DEV_ID) -> bytes:
    return build_packet(device_id, PWD, Func.RESPONSE, data)


def _func_byte(pkt: bytes) -> int:
    id_size = pkt[3]
    pwd_size = pkt[4 + id_size]
    return pkt[4 + id_size + 1 + pwd_size]


class FakeTransport:
    """Scripted transport: pops one item per send_recv call.

    Items may be bytes (a response packet) or an exception to raise.
    send_only records fire-and-forget packets without responses.
    """

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.sent = []
        self.sent_only = []

    def send_recv(self, host, packet, port=4000, timeout=None):
        self.sent.append(bytes(packet))
        item = self.responses.pop(0) if self.responses else VentoTimeoutError("no scripted response")
        if isinstance(item, Exception):
            raise item
        return item

    def send_only(self, host, packet, port=4000):
        self.sent_only.append(bytes(packet))


class FakeAsyncTransport:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.sent = []
        self.sent_only = []

    async def send_recv(self, host, packet, port=4000, timeout=None):
        self.sent.append(bytes(packet))
        item = self.responses.pop(0) if self.responses else VentoTimeoutError("no scripted response")
        if isinstance(item, Exception):
            raise item
        return item

    async def send_only(self, host, packet, port=4000):
        self.sent_only.append(bytes(packet))


def _client(fake):
    client = VentoClient(HOST, DEV_ID, PWD)
    client._transport = fake
    return client


def _async_client(fake):
    client = AsyncVentoClient(HOST, DEV_ID, PWD)
    client._transport = fake
    return client


class TestVerifiedWrite:
    def test_verified_write_returns_applied_echo(self):
        fake = FakeTransport([_ack(bytes([0x02, 0x02]))])
        result = _client(fake).write_params({Param.SPEED: 2})
        assert result == {Param.SPEED: b"\x02"}

    def test_verified_write_uses_func_03(self):
        fake = FakeTransport([_ack(bytes([0x02, 0x02]))])
        _client(fake).write_params({Param.SPEED: 2})
        assert len(fake.sent) == 1
        assert _func_byte(fake.sent[0]) == int(Func.WRITE_RESP)

    def test_clamped_echo_returns_actual_value(self):
        """Live evidence: writing HUMIDITY_THRESHOLD=30 (below valid range 40-80)
        made the controller apply and echo 40. The applied value is reported, not
        the requested one, and no error is raised."""
        fake = FakeTransport([_ack(bytes([0x19, 0x28]))])  # echo: 40
        result = _client(fake).write_params({Param.HUMIDITY_THRESHOLD: 30})
        assert result == {Param.HUMIDITY_THRESHOLD: b"\x28"}

    def test_verified_write_retries_on_timeout(self):
        """~3% measured UDP loss: a lost ack must trigger a re-send."""
        fake = FakeTransport(
            [
                VentoTimeoutError("lost 1"),
                VentoTimeoutError("lost 2"),
                _ack(bytes([0x02, 0x02])),
            ]
        )
        result = _client(fake).write_params({Param.SPEED: 2})
        assert result == {Param.SPEED: b"\x02"}
        assert len(fake.sent) == 3
        assert len(set(fake.sent)) == 1  # identical packet re-sent

    def test_verified_write_raises_ack_error_after_all_attempts(self):
        fake = FakeTransport([VentoTimeoutError("down")] * 5)
        with pytest.raises(VentoAckError):
            _client(fake).write_params({Param.SPEED: 2})
        assert len(fake.sent) == 3  # default attempt budget

    def test_ack_error_reports_attempts(self):
        fake = FakeTransport([VentoTimeoutError("down")] * 5)
        with pytest.raises(VentoAckError) as ei:
            _client(fake).write_params({Param.SPEED: 2})
        assert ei.value.attempts == 3

    def test_invert_value_write_single_attempt(self):
        """POWER=2 means "invert". A retry after a lost ack would toggle back,
        so invert writes get exactly one attempt."""
        fake = FakeTransport([VentoTimeoutError("lost")] * 5)
        with pytest.raises(VentoAckError) as ei:
            _client(fake).write_params({Param.POWER: 2})
        assert len(fake.sent) == 1
        assert ei.value.attempts == 1

    def test_speed_two_is_not_treated_as_invert(self):
        """SPEED=2 is a plain value (speed 2), not an invert command - the
        no-retry rule must only apply to params with invert semantics."""
        fake = FakeTransport([VentoTimeoutError("lost 1"), _ack(bytes([0x02, 0x02]))])
        _client(fake).write_params({Param.SPEED: 2})
        assert len(fake.sent) == 2


class TestWriteOnlyRouting:
    def test_w_only_write_fire_and_forget(self):
        """W-only params have no readable state; FUNC 0x02 is their only spec'd
        function. The write returns an empty mapping (unverifiable)."""
        fake = FakeTransport()
        result = _client(fake).write_params({Param.FILTER_RESET: 1})
        assert result == {}
        assert len(fake.sent_only) == 1
        assert fake.sent == []
        assert _func_byte(fake.sent_only[0]) == int(Func.WRITE)

    def test_mixed_rw_and_w_only_rejected(self):
        fake = FakeTransport()
        with pytest.raises(VentoCapabilityError):
            _client(fake).write_params({Param.SPEED: 1, Param.FILTER_RESET: 1})
        assert fake.sent == [] and fake.sent_only == []

    def test_write_read_only_param_rejected(self):
        fake = FakeTransport()
        with pytest.raises(VentoCapabilityError):
            _client(fake).write_params({Param.FIRMWARE_VERSION: b"\x01"})
        assert fake.sent == [] and fake.sent_only == []

    def test_empty_write_map_no_traffic(self):
        fake = FakeTransport()
        assert _client(fake).write_params({}) == {}
        assert fake.sent == [] and fake.sent_only == []


class TestNegativeAcks:
    def test_unsupported_param_ack_raises_with_applied(self):
        """Live ack data=0201fd90: SPEED applied, 0x90 rejected. The error must
        carry the applied subset so callers know what took effect."""
        fake = FakeTransport([_ack(bytes([0x02, 0x01, 0xFD, 0x90]))])
        with pytest.raises(VentoUnsupportedParamError) as ei:
            _client(fake).write_params({Param.SPEED: 1, 0x90: b"\x01"})
        assert ei.value.applied == {Param.SPEED: b"\x01"}

    def test_wrong_device_ack_raises_mismatch(self):
        """An ack whose device ID does not match the request is a protocol
        anomaly: raise immediately, no retry."""
        fake = FakeTransport([_ack(bytes([0x02, 0x02]), device_id=OTHER_ID)])
        with pytest.raises(VentoAckMismatchError):
            _client(fake).write_params({Param.SPEED: 2})
        assert len(fake.sent) == 1


class TestScheduleDaySelectors:
    """Datasheet: schedule day byte 0 (all days), 8 (Mon-Fri), 9 (Sat-Sun) are
    write-only selectors; reads only accept 1-7."""

    def _schedule_echo(self, day: int) -> bytes:
        """Echo ack for a SCHEDULE_SETUP write: 6-byte value via 0xFE size cmd."""
        return _ack(bytes([0xFE, 0x06, 0x77, day, 1, 1, 0, 0, 8]))

    def test_schedule_write_accepts_day_zero(self):
        fake = FakeTransport([self._schedule_echo(0)])
        _client(fake).set_schedule_period(0, 1, 1, 8, 0)

    def test_schedule_write_accepts_day_nine(self):
        fake = FakeTransport([self._schedule_echo(9)])
        _client(fake).set_schedule_period(9, 1, 1, 8, 0)

    def test_schedule_read_rejects_day_zero(self):
        with pytest.raises(VentoValueError):
            _client(FakeTransport()).get_schedule_period(0, 1)


class TestAsyncVerifiedWrite:
    async def test_async_verified_write_returns_applied_echo(self):
        fake = FakeAsyncTransport([_ack(bytes([0x02, 0x02]))])
        result = await _async_client(fake).write_params({Param.SPEED: 2})
        assert result == {Param.SPEED: b"\x02"}
        assert _func_byte(fake.sent[0]) == int(Func.WRITE_RESP)

    async def test_async_verified_write_retries_on_timeout(self):
        fake = FakeAsyncTransport(
            [
                VentoTimeoutError("lost 1"),
                VentoTimeoutError("lost 2"),
                _ack(bytes([0x02, 0x02])),
            ]
        )
        result = await _async_client(fake).write_params({Param.SPEED: 2})
        assert result == {Param.SPEED: b"\x02"}
        assert len(fake.sent) == 3

    async def test_async_w_only_write_fire_and_forget(self):
        fake = FakeAsyncTransport()
        result = await _async_client(fake).write_params({Param.FACTORY_RESET: 1})
        assert result == {}
        assert len(fake.sent_only) == 1
        assert fake.sent == []

    async def test_async_invert_single_attempt(self):
        fake = FakeAsyncTransport([VentoTimeoutError("lost")] * 5)
        with pytest.raises(VentoAckError) as ei:
            await _async_client(fake).write_params({Param.POWER: 2})
        assert len(fake.sent) == 1
        assert ei.value.attempts == 1
