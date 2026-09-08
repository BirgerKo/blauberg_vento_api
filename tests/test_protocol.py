import pytest
from blauberg_vento.exceptions import VentoChecksumError, VentoUnsupportedParamError
from blauberg_vento.parameters import Func, Param
from blauberg_vento.protocol import (
    build_discovery,
    build_packet,
    build_read,
    decode_filter_countdown,
    decode_firmware,
    decode_ip,
    decode_machine_hours,
    decode_rtc_calendar,
    decode_rtc_time,
    decode_schedule,
    encode_ip,
    parse_response,
    verify_checksum,
)

NULL_ID = b"\x00" * 16
NULL_PWD = "1111"

SPEC_RQ = bytes(
    [
        0xFD,
        0xFD,
        0x02,
        0x10,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0x04,
        0x31,
        0x31,
        0x31,
        0x31,
        0x01,
        0x01,
        0x02,
        0xDE,
        0x00,
    ]
)

SPEC_RS = bytes(
    [
        0xFD,
        0xFD,
        0x02,
        0x10,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0x04,
        0x31,
        0x31,
        0x31,
        0x31,
        0x06,
        0x01,
        0x00,
        0x02,
        0x03,
        0xE6,
        0x00,
    ]
)


def _mkr(data):
    return build_packet(NULL_ID, NULL_PWD, Func.RESPONSE, data)


class TestChecksum:
    def test_spec_rq(self):
        verify_checksum(SPEC_RQ)

    def test_spec_rs(self):
        verify_checksum(SPEC_RS)

    def test_bad_checksum(self):
        bad = bytearray(SPEC_RQ)
        bad[-1] ^= 0xFF
        with pytest.raises(VentoChecksumError):
            verify_checksum(bytes(bad))


class TestBuilding:
    def test_matches_spec(self):
        assert build_read(NULL_ID, NULL_PWD, [Param.POWER, Param.SPEED]) == SPEC_RQ

    def test_starts_fd_fd(self):
        assert build_read(NULL_ID, NULL_PWD, [Param.POWER])[:2] == b"\xfd\xfd"

    def test_checksum_valid(self):
        verify_checksum(build_read(NULL_ID, NULL_PWD, [Param.POWER, Param.SPEED]))

    def test_discovery_default_id(self):
        assert build_discovery()[4:20] == b"DEFAULT_DEVICEID"

    def test_night_timer_page_cmd(self):
        pkt = build_read(NULL_ID, NULL_PWD, [Param.NIGHT_TIMER])
        raw = pkt[2:-2]
        idx = raw.index(0xFF)
        assert raw[idx + 1] == 0x03 and raw[idx + 2] == 0x02

    def test_bad_id_raises(self):
        with pytest.raises(Exception):
            build_read(b"SHORT", NULL_PWD, [Param.POWER])

    def test_long_password_raises(self):
        with pytest.raises(Exception):
            build_read(NULL_ID, "TOOLONGPWD", [Param.POWER])


class TestParsing:
    def test_spec_response(self):
        r = parse_response(SPEC_RS)
        assert r[Param.POWER] == b"\x00" and r[Param.SPEED] == b"\x03"

    def test_unsupported_param(self):
        with pytest.raises(VentoUnsupportedParamError) as ei:
            parse_response(_mkr(bytes([0xFD, 0x01, 0x02, 0x03])))
        assert 0x0001 in ei.value.params

    def test_size_override(self):
        r = parse_response(_mkr(bytes([0xFE, 0x02, 0x24, 0x88, 0x13])))
        assert int.from_bytes(r[Param.BATTERY_VOLTAGE], "little") == 5000

    def test_page_change(self):
        r = parse_response(_mkr(bytes([0xFF, 0x03, 0xFE, 0x02, 0x02, 0x1E, 0x08])))
        v = r[Param.NIGHT_TIMER]
        assert v[0] == 30 and v[1] == 8


class TestDecoders:
    def test_decode_ip(self):
        assert decode_ip(bytes([192, 168, 1, 50])) == "192.168.1.50"

    def test_encode_ip(self):
        assert encode_ip("192.168.1.50") == bytes([192, 168, 1, 50])

    def test_firmware(self):
        v = decode_firmware(bytes([1, 5, 14, 3, 0xE8, 0x07]))
        assert v == {"major": 1, "minor": 5, "day": 14, "month": 3, "year": 2024}

    def test_machine_hours(self):
        v = decode_machine_hours(bytes([30, 5, 10, 0]))
        assert v == {"minutes": 30, "hours": 5, "days": 10}

    def test_rtc_time(self):
        v = decode_rtc_time(bytes([45, 30, 14]))
        assert v == {"seconds": 45, "minutes": 30, "hours": 14}

    def test_rtc_calendar(self):
        v = decode_rtc_calendar(bytes([15, 3, 6, 24]))
        assert v["year"] == 2024 and v["month"] == 6

    def test_schedule(self):
        v = decode_schedule(bytes([2, 1, 2, 0, 30, 8]))
        assert v["speed"] == 2 and v["end_hours"] == 8 and v["end_minutes"] == 30

    def test_filter_countdown(self):
        v = decode_filter_countdown(bytes([0, 12, 90]))
        assert v == {"minutes": 0, "hours": 12, "days": 90}

    def test_bad_ip_size(self):
        with pytest.raises(Exception):
            decode_ip(b"\xc0\xa8")


class TestValidation:
    def _c(self):
        from blauberg_vento import VentoClient

        return VentoClient("127.0.0.1", NULL_ID.decode("ascii"))

    def test_bad_speed(self):
        from blauberg_vento import VentoValueError

        with pytest.raises(VentoValueError):
            self._c().set_speed(5)

    def test_bad_humidity_threshold(self):
        from blauberg_vento import VentoValueError

        with pytest.raises(VentoValueError):
            self._c().set_humidity_threshold(100)

    def test_bad_boost_delay(self):
        from blauberg_vento import VentoValueError

        with pytest.raises(VentoValueError):
            self._c().set_boost_delay(61)

    def test_long_password(self):
        from blauberg_vento import VentoValueError

        with pytest.raises(VentoValueError):
            self._c().change_password("TOOLONGPWD")

    def test_manual_speed_boundaries(self):
        from unittest.mock import patch

        c = self._c()
        with patch.object(c._transport, "send_only"):
            c.set_manual_speed(0)
            c.set_manual_speed(255)
