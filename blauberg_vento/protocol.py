"""
Blauberg Vento Protocol Implementation

This module handles the low-level protocol for communicating with Blauberg Vento devices.
It includes:
- Packet construction (`build_packet`, `build_read`, `build_write`).
- Response parsing (`parse_response`, `_parse_data_bytes`).
- Checksum verification (`verify_checksum`).
- Data encoding/decoding (e.g., `decode_int`, `decode_ip`, `decode_firmware`).

Key Functions:
- `build_read(device_id, password, params)`: Build a packet to read parameters.
- `build_write(device_id, password, param_values)`: Build a packet to write parameters.
- `parse_response(raw)`: Parse a raw response packet into a dictionary of parameter values.

Usage Example:
    packet = build_read(device_id="DEVICE_ID", password="1111", params=[Param.POWER])
    response = transport.send_recv("192.168.1.100", packet)
    parsed = parse_response(response)
"""

from __future__ import annotations

import struct
from typing import NamedTuple

from .exceptions import VentoChecksumError, VentoProtocolError, VentoUnsupportedParamError
from .parameters import (
    CMD_FUNC,
    CMD_NOT_SUP,
    CMD_PAGE,
    CMD_SIZE,
    DEFAULT_DEVICE_ID,
    MAX_PACKET_SIZE,
    PACKET_START,
    PROTOCOL_TYPE,
    Func,
    Param,
    param_size,
)

ParamValue = int | bytes
ParamValues = dict[Param, ParamValue]
ResponseValues = dict[Param | int, bytes]


def _encode_id(device_id: str | bytes) -> bytes:
    raw = device_id.encode("ascii") if isinstance(device_id, str) else device_id
    if len(raw) != 16:
        raise VentoProtocolError(f"Device ID must be 16 chars, got {len(raw)}")
    return raw


def _encode_password(password: str) -> bytes:
    try:
        raw = password.encode("ascii")
    except UnicodeEncodeError as exc:
        raise VentoProtocolError("Password must contain ASCII characters") from exc
    if len(raw) > 8:
        raise VentoProtocolError("Password max 8 chars")
    return raw


def _checksum(payload: bytes) -> bytes:
    return struct.pack("<H", sum(payload) & 0xFFFF)


def _param_high_low(param: Param) -> tuple[int, int]:
    value = int(param)
    return (value >> 8) & 0xFF, value & 0xFF


def build_packet(device_id: str | bytes, password: str, func: Func, data: bytes) -> bytes:
    id_bytes = _encode_id(device_id)
    pwd_bytes = _encode_password(password)
    payload = (
        bytes([PROTOCOL_TYPE])
        + bytes([len(id_bytes)])
        + id_bytes
        + bytes([len(pwd_bytes)])
        + pwd_bytes
        + bytes([int(func)])
        + data
    )
    pkt = PACKET_START + payload + _checksum(payload)
    if len(pkt) > MAX_PACKET_SIZE:
        raise VentoProtocolError(f"Packet {len(pkt)} > {MAX_PACKET_SIZE}")
    return pkt


def _build_read_data(params: list[Param]) -> bytes:
    data = bytearray()
    page = 0x00
    for p in params:
        high, low = _param_high_low(p)
        if high != page:
            data += bytes([CMD_PAGE, high])
            page = high
        data.append(low)
    return bytes(data)


def _build_write_data(param_values: dict[Param, int | bytes]) -> bytes:
    data = bytearray()
    page = 0x00
    for p, val in param_values.items():
        high, low = _param_high_low(p)
        expected_size = param_size(p)
        if isinstance(val, int):
            if expected_size is None:
                raise VentoProtocolError(f"{p.name} needs bytes, not int")
            try:
                val_bytes = val.to_bytes(expected_size, "little")
            except OverflowError as exc:
                raise VentoProtocolError(f"{p.name} value does not fit in {expected_size} bytes") from exc
        else:
            val_bytes = bytes(val)
        actual_size = len(val_bytes)
        if expected_size is not None and actual_size != expected_size:
            raise VentoProtocolError(f"{p.name} needs exactly {expected_size} bytes, got {actual_size}")
        if actual_size > 0xFF:
            raise VentoProtocolError(f"{p.name} value is too large: {actual_size} bytes")
        if high != page:
            data += bytes([CMD_PAGE, high])
            page = high
        if actual_size != 1:
            data += bytes([CMD_SIZE, actual_size])
        data.append(low)
        data += val_bytes
    return bytes(data)


def build_read(device_id: str | bytes, password: str, params: list[Param]) -> bytes:
    return build_packet(device_id, password, Func.READ, _build_read_data(params))


def build_write(device_id: str | bytes, password: str, pv: ParamValues) -> bytes:
    return build_packet(device_id, password, Func.WRITE, _build_write_data(pv))


def build_write_resp(device_id: str | bytes, password: str, pv: ParamValues) -> bytes:
    return build_packet(device_id, password, Func.WRITE_RESP, _build_write_data(pv))


def build_increment(device_id: str | bytes, password: str, params: list[Param]) -> bytes:
    return build_packet(device_id, password, Func.INCREMENT, _build_read_data(params))


def build_decrement(device_id: str | bytes, password: str, params: list[Param]) -> bytes:
    return build_packet(device_id, password, Func.DECREMENT, _build_read_data(params))


def build_discovery() -> bytes:
    return build_read(DEFAULT_DEVICE_ID, "", [Param.DEVICE_SEARCH, Param.UNIT_TYPE])


def verify_checksum(raw: bytes) -> None:
    if len(raw) < 4:
        raise VentoProtocolError("Packet too short")
    if raw[0] != 0xFD or raw[1] != 0xFD:
        raise VentoProtocolError("Missing 0xFD 0xFD header")
    if len(raw) < 23:
        raise VentoProtocolError(f"Packet too short: {len(raw)}")
    expected = struct.unpack("<H", raw[-2:])[0]
    actual = sum(raw[2:-2]) & 0xFFFF
    if actual != expected:
        raise VentoChecksumError(f"Checksum mismatch: {actual:#06x} != {expected:#06x}")


class _PacketHeader(NamedTuple):
    """Parsed fields from the fixed-length header of a Blauberg Vento UDP packet."""

    data_start: int
    device_id: bytes
    password: bytes
    func_byte: int


def _parse_packet_header(raw: bytes) -> _PacketHeader:
    """Validate the packet framing and extract header fields."""
    if len(raw) < 23:
        raise VentoProtocolError(f"Packet too short: {len(raw)}")
    if raw[0] != 0xFD or raw[1] != 0xFD:
        raise VentoProtocolError("Missing 0xFD 0xFD header")
    if raw[2] != PROTOCOL_TYPE:
        raise VentoProtocolError(f"Unknown type {raw[2]:#04x}")
    id_size = raw[3]
    if id_size != 16:
        raise VentoProtocolError(f"Invalid device ID length: {id_size}")
    id_end = 4 + id_size
    if id_end >= len(raw) - 2:
        raise VentoProtocolError("Packet missing password length")
    pwd_size = raw[id_end]
    if pwd_size > 8:
        raise VentoProtocolError(f"Invalid password length: {pwd_size}")
    pwd_end = id_end + 1 + pwd_size
    if pwd_end >= len(raw) - 2:
        raise VentoProtocolError("Packet missing function byte")
    func_byte = raw[pwd_end]
    return _PacketHeader(
        data_start=pwd_end + 1,
        device_id=raw[4:id_end],
        password=raw[id_end + 1 : pwd_end],
        func_byte=func_byte,
    )


def parse_response(raw: bytes) -> ResponseValues:
    header = _parse_packet_header(raw)
    if header.func_byte != int(Func.RESPONSE):
        raise VentoProtocolError(f"Expected FUNC=0x06, got {header.func_byte:#04x}")
    if header.data_start >= len(raw) - 2:
        raise VentoProtocolError("Response packet missing payload data")
    verify_checksum(raw)
    return _parse_data_bytes(raw[header.data_start : -2])


def _parse_data_bytes(data: bytes) -> ResponseValues:
    """Walk the TLV-like data section of a response packet and return a param → bytes mapping."""
    result: ResponseValues = {}
    unsupported: list[int] = []
    page = 0x00
    i = 0
    param_size = 1

    while i < len(data):
        b = data[i]

        if b == CMD_PAGE:
            if i + 1 >= len(data):
                raise VentoProtocolError("Page command missing page number")
            i += 1
            page = data[i]
            i += 1
            param_size = 1
            continue

        if b == CMD_FUNC:
            if i + 1 >= len(data):
                raise VentoProtocolError("Function command missing function value")
            i += 2
            param_size = 1
            continue

        if b == CMD_SIZE:
            if i + 1 >= len(data):
                raise VentoProtocolError("Size command missing size value")
            i += 1
            param_size = data[i]
            if param_size == 0:
                raise VentoProtocolError("Parameter size must be greater than zero")
            i += 1
            if i >= len(data):
                raise VentoProtocolError("Size command missing parameter")
            b = data[i]

        if b == CMD_NOT_SUP:
            if i + 1 >= len(data):
                raise VentoProtocolError("Unsupported parameter command is truncated")
            i += 1
            unsupported.append((page << 8) | data[i])
            i += 1
            param_size = 1
            continue

        param_num = (page << 8) | b
        i += 1
        value_end = i + param_size
        if value_end > len(data):
            raise VentoProtocolError(f"Param {param_num:#06x} truncated")
        value_bytes = bytes(data[i:value_end])
        i = value_end

        try:
            result[Param(param_num)] = value_bytes
        except ValueError:
            result[param_num] = value_bytes

        param_size = 1

    if unsupported:
        raise VentoUnsupportedParamError(unsupported)
    return result


def decode_int(val: bytes) -> int:
    return int.from_bytes(val, "little")


def decode_ip(val: bytes) -> str:
    if len(val) != 4:
        raise VentoProtocolError("IP must be 4 bytes")
    return ".".join(str(b) for b in val)


def encode_ip(ip: str) -> bytes:
    parts = ip.split(".")
    if len(parts) != 4:
        raise VentoProtocolError(f"Invalid IP {ip!r}")
    return bytes(int(p) for p in parts)


def decode_text(val: bytes) -> str:
    return val.decode("ascii", errors="replace")


def decode_firmware(val: bytes) -> dict[str, int]:
    if len(val) != 6:
        raise VentoProtocolError("Firmware must be 6 bytes")
    return {
        "major": val[0],
        "minor": val[1],
        "day": val[2],
        "month": val[3],
        "year": int.from_bytes(val[4:6], "little"),
    }


def decode_machine_hours(val: bytes) -> dict[str, int]:
    if len(val) != 4:
        raise VentoProtocolError("Machine hours must be 4 bytes")
    return {"minutes": val[0], "hours": val[1], "days": int.from_bytes(val[2:4], "little")}


def decode_rtc_time(val: bytes) -> dict[str, int]:
    if len(val) != 3:
        raise VentoProtocolError("RTC time must be 3 bytes")
    return {"seconds": val[0], "minutes": val[1], "hours": val[2]}


def decode_rtc_calendar(val: bytes) -> dict[str, int]:
    if len(val) != 4:
        raise VentoProtocolError("RTC calendar must be 4 bytes")
    return {"day": val[0], "day_of_week": val[1], "month": val[2], "year": 2000 + val[3]}


def decode_schedule(val: bytes) -> dict[str, int]:
    if len(val) != 6:
        raise VentoProtocolError("Schedule must be 6 bytes")
    return {
        "day_of_week": val[0],
        "period": val[1],
        "speed": val[2],
        "_reserved": val[3],
        "end_minutes": val[4],
        "end_hours": val[5],
    }


def decode_timer_countdown(val: bytes) -> dict[str, int]:
    if len(val) != 3:
        raise VentoProtocolError("Timer countdown must be 3 bytes")
    return {"seconds": val[0], "minutes": val[1], "hours": val[2]}


def decode_filter_countdown(val: bytes) -> dict[str, int]:
    if len(val) != 3:
        raise VentoProtocolError("Filter countdown must be 3 bytes")
    return {"minutes": val[0], "hours": val[1], "days": val[2]}
