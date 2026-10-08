"""Tests for the robust-ack protocol layer.

Target API (TDD - these tests define the contract to implement):
- parse_response accepts empty-data 0x06 acks (write-only param acks).
- parse_response optionally correlates the ack's device ID with the request.
- VentoUnsupportedParamError carries the applied params from mixed acks.
- Write-path capability validation per PARAM_META:
  * FUNC 0x02 (build_write)      -> W-only params only.
  * FUNC 0x03 (build_write_resp) -> any writable param (RW or W-only).
  * Read-only params are rejected by both write paths.
  * W-only params are rejected by build_read.
  * Unknown params pass through both write paths and reads: the controller's
    0xFD negative ack is the capability source of truth (probing).
- param_size() returns None for unknown params instead of raising KeyError.
"""

import pytest
from blauberg_vento.exceptions import (
    VentoAckMismatchError,
    VentoCapabilityError,
    VentoUnsupportedParamError,
)
from blauberg_vento.parameters import Func, Param, param_size
from blauberg_vento.protocol import build_packet, build_read, build_write, build_write_resp, parse_response

DEV_ID = "002D003957425711"
OTHER_ID = "1122334455667788"
PWD = "1111"


def _ack(data: bytes, device_id: str = DEV_ID) -> bytes:
    return build_packet(device_id, PWD, Func.RESPONSE, data)


def _func_byte(pkt: bytes) -> int:
    id_size = pkt[3]
    pwd_size = pkt[4 + id_size]
    return pkt[4 + id_size + 1 + pwd_size]


class TestEmptyAckParsing:
    """Live evidence: a 0x03 write to a W-only param (RESET_ALARMS, 128) makes the
    controller answer with a 0x06 packet whose data section is EMPTY. The parser
    must return an empty mapping instead of raising."""

    def test_empty_response_ack_returns_empty_dict(self):
        assert parse_response(_ack(b"")) == {}

    def test_empty_response_ack_with_matching_expected_id(self):
        assert parse_response(_ack(b""), expected_device_id=DEV_ID) == {}


class TestMixedAckAppliedValues:
    """Live evidence: mixed ack data=0201fd90 means SPEED was applied (01) and 0x90
    is unsupported. The raised error must expose the applied values, not discard them."""

    def test_unsupported_param_error_carries_applied_values(self):
        with pytest.raises(VentoUnsupportedParamError) as ei:
            parse_response(_ack(bytes([0x02, 0x01, 0xFD, 0x90])))
        assert ei.value.params == [0x90]
        assert ei.value.applied == {Param.SPEED: b"\x01"}

    def test_unsupported_param_error_applied_defaults_empty(self):
        with pytest.raises(VentoUnsupportedParamError) as ei:
            parse_response(_ack(bytes([0xFD, 0x90])))
        assert ei.value.params == [0x90]
        assert ei.value.applied == {}


class TestAckDeviceIdCorrelation:
    """The protocol has no transaction ID; the header device ID is the only
    correlation key. An ack from a different device must not be accepted."""

    def test_parse_response_rejects_wrong_device_id(self):
        with pytest.raises(VentoAckMismatchError):
            parse_response(_ack(bytes([0x02, 0x01]), device_id=OTHER_ID), expected_device_id=DEV_ID)

    def test_parse_response_accepts_matching_expected_id(self):
        result = parse_response(_ack(bytes([0x02, 0x01])), expected_device_id=DEV_ID)
        assert result[Param.SPEED] == b"\x01"

    def test_parse_response_without_expected_id_accepts_any_device(self):
        result = parse_response(_ack(bytes([0x02, 0x01]), device_id=OTHER_ID))
        assert result[Param.SPEED] == b"\x01"


class TestWriteCapabilityValidation:
    """Policy: where a parameter is RW-capable the library shall not allow plain
    W (FUNC 0x02). Verified writes (FUNC 0x03) are the only permitted write for
    RW params. Write-only params keep FUNC 0x02. Read-only params are never writable."""

    def test_build_write_rejects_rw_param(self):
        with pytest.raises(VentoCapabilityError):
            build_write(DEV_ID, PWD, {Param.POWER: 1})

    def test_build_write_allows_w_only_param(self):
        pkt = build_write(DEV_ID, PWD, {Param.FILTER_RESET: 1})
        assert _func_byte(pkt) == int(Func.WRITE)

    def test_build_write_rejects_read_only_param(self):
        with pytest.raises(VentoCapabilityError):
            build_write(DEV_ID, PWD, {Param.FIRMWARE_VERSION: b"\x01"})

    def test_build_write_allows_unknown_param_for_probing(self):
        """Unknown capabilities are the device's business: the controller's
        0xFD negative ack is the source of truth for probing writes."""
        pkt = build_write(DEV_ID, PWD, {0x0090: b"\x01"})
        assert _func_byte(pkt) == int(Func.WRITE)

    def test_build_write_resp_allows_rw_param(self):
        pkt = build_write_resp(DEV_ID, PWD, {Param.SPEED: 2})
        assert _func_byte(pkt) == int(Func.WRITE_RESP)

    def test_build_write_resp_allows_w_only_param(self):
        pkt = build_write_resp(DEV_ID, PWD, {Param.RESET_ALARMS: b"\x01"})
        assert _func_byte(pkt) == int(Func.WRITE_RESP)

    def test_build_write_resp_rejects_read_only_param(self):
        with pytest.raises(VentoCapabilityError):
            build_write_resp(DEV_ID, PWD, {Param.UNIT_TYPE: b"\x01"})

    def test_build_write_resp_allows_unknown_param_for_probing(self):
        pkt = build_write_resp(DEV_ID, PWD, {0x0090: b"\x01"})
        assert _func_byte(pkt) == int(Func.WRITE_RESP)


class TestReadCapabilityValidation:
    """Symmetric rule on the read side: W-only params cannot be read at all
    (the controller would answer 0xFD). Unknown params stay readable so
    capability probing via negative acks keeps working."""

    def test_build_read_rejects_w_only_param(self):
        with pytest.raises(VentoCapabilityError):
            build_read(DEV_ID, PWD, [Param.FACTORY_RESET])

    def test_build_read_allows_unknown_param_for_probing(self):
        pkt = build_read(DEV_ID, PWD, [0x0090])
        assert _func_byte(pkt) == int(Func.READ)


class TestParamSizeRobustness:
    """Live evidence: param_size() raised a bare KeyError for param 0x90, blocking
    probe packet construction. Unknown params must yield None."""

    def test_param_size_unknown_returns_none(self):
        assert param_size(0x0090) is None

    def test_param_size_known_param(self):
        assert param_size(Param.POWER) == 1
