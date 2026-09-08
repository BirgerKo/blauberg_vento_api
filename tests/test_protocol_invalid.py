import pytest
from blauberg_vento.exceptions import VentoChecksumError, VentoProtocolError
from blauberg_vento.parameters import Func, Param
from blauberg_vento.protocol import (
    _parse_data_bytes,
    build_packet,
    build_write,
    parse_response,
    verify_checksum,
)


@pytest.mark.parametrize(
    "raw, expected_error",
    [
        (b"\xfd\xfd\x02\x10", VentoProtocolError),
        (b"\x00\x00\x00\x00", VentoProtocolError),
        (b"\xfd\xfd\x02\x10" + b"\x00" * 16 + b"\x00\x06" + b"\x00\x00", VentoChecksumError),
    ],
)
def test_invalid_packet_rejections(raw: bytes, expected_error: type[Exception]) -> None:
    with pytest.raises(expected_error):
        if len(raw) >= 4 and raw[:2] == b"\xfd\xfd":
            verify_checksum(raw)
        parse_response(raw)


def test_parse_response_rejects_truncated_packet() -> None:
    raw = b"\xfd\xfd\x02\x10" + b"\x00" * 16 + b"\x00\x06" + b"\x00\x00"
    with pytest.raises(VentoProtocolError):
        parse_response(raw)


@pytest.mark.parametrize(
    "raw",
    [
        b"\xfd\xfd\x02\x00" + b"\x00" * 19,
        b"\xfd\xfd\x02\x10" + b"\x00" * 16 + b"\x09" + b"\x00" * 9 + b"\x00\x00",
    ],
)
def test_parse_response_rejects_invalid_header_lengths(raw: bytes) -> None:
    with pytest.raises(VentoProtocolError):
        parse_response(raw)


@pytest.mark.parametrize(
    "data",
    [b"\xff", b"\xfe", b"\xfe\x00", b"\xfd"],
)
def test_parse_data_bytes_rejects_truncated_control_commands(data: bytes) -> None:
    with pytest.raises(VentoProtocolError):
        _parse_data_bytes(data)


def test_build_write_rejects_wrong_fixed_size() -> None:
    with pytest.raises(VentoProtocolError):
        build_write(b"\x00" * 16, "1111", {Param.NIGHT_TIMER: b"\x01"})


def test_build_write_rejects_integer_overflow() -> None:
    with pytest.raises(VentoProtocolError):
        build_write(b"\x00" * 16, "1111", {Param.POWER: 256})


def test_build_packet_rejects_non_ascii_password() -> None:
    with pytest.raises(VentoProtocolError):
        build_packet(b"\x00" * 16, "päss", Func.READ, b"")
