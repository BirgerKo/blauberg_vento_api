"""
Blauberg Vento Client Implementation

This module provides the main client classes for interacting with Blauberg Vento devices.
It supports:
- Synchronous (`VentoClient`) and asynchronous (`AsyncVentoClient`) communication.
- Reading and writing device parameters (e.g., power, speed, timers, sensors).
- Device discovery via UDP broadcast.
- Helper methods for common operations (e.g., turning on/off, setting speed, configuring Wi-Fi).

Key Classes:
- `VentoClient`: Synchronous client for direct device control.
- `AsyncVentoClient`: Asynchronous client for non-blocking operations.
- `_DeviceStateBuilder`: Internal helper to construct `DeviceState` from raw parameter data.

Usage Example:
    client = VentoClient(host="192.168.1.100", device_id="DEVICE_ID", password="1111")
    state = client.get_state()
    client.turn_on()
"""
from __future__ import annotations

import logging
from datetime import datetime

from .exceptions import VentoUnsupportedParamError, VentoValueError
from .models import (
    DeviceState,
    DiscoveredDevice,
    FilterCountdown,
    FirmwareVersion,
    MachineHours,
    RtcCalendar,
    RtcTime,
    SchedulePeriod,
    TimerCountdown,
    WifiConfig,
)
from .parameters import DEFAULT_PORT, Param
from .protocol import (
    build_decrement,
    build_discovery,
    build_increment,
    build_read,
    build_write,
    build_write_resp,
    decode_filter_countdown,
    decode_firmware,
    decode_int,
    decode_ip,
    decode_machine_hours,
    decode_rtc_calendar,
    decode_rtc_time,
    decode_schedule,
    decode_text,
    decode_timer_countdown,
    encode_ip,
    parse_response,
)
from .transport import AsyncVentoTransport, VentoTransport

log = logging.getLogger(__name__)

DiscoveryItem = dict[str, str | bytes]
RawParamMap = dict[Param | int, bytes]
ParamWriteMap = dict[Param, int | bytes]


def _check_range(name: str, value: int, low: int, high: int) -> None:
    if not low <= value <= high:
        raise VentoValueError(f"{name} must be in [{low},{high}], got {value}")


def _check_choices(name: str, value: int, choices: set[int]) -> None:
    if value not in choices:
        raise VentoValueError(f"{name} must be one of {sorted(choices)}, got {value}")


_BASIC_STATUS_PARAMS = [
    Param.POWER,
    Param.SPEED,
    Param.BOOST_STATUS,
    Param.TIMER_MODE,
    Param.TIMER_COUNTDOWN,
    Param.HUMIDITY_SENSOR,
    Param.RELAY_SENSOR,
    Param.VOLTAGE_SENSOR,
    Param.HUMIDITY_THRESHOLD,
    Param.VOLTAGE_THRESHOLD,
    Param.BATTERY_VOLTAGE,
    Param.CURRENT_HUMIDITY,
    Param.VOLTAGE_SENSOR_VAL,
    Param.RELAY_STATE,
    Param.MANUAL_SPEED,
    Param.FAN1_SPEED,
    Param.FAN2_SPEED,
]
_EXTENDED_CONFIG_PARAMS = [
    Param.FILTER_COUNTDOWN,
    Param.FILTER_INDICATOR,
    Param.BOOST_DELAY,
    Param.RTC_TIME,
    Param.RTC_CALENDAR,
    Param.WEEKLY_SCHEDULE_EN,
    Param.DEVICE_SEARCH,
    Param.MACHINE_HOURS,
    Param.ALARM_STATUS,
    Param.CLOUD_PERMISSION,
    Param.FIRMWARE_VERSION,
    Param.OPERATION_MODE,
    Param.UNIT_TYPE,
]
_WIFI_PARAMS = [
    Param.WIFI_MODE,
    Param.WIFI_SSID,
    Param.WIFI_ENCRYPTION,
    Param.WIFI_CHANNEL,
    Param.WIFI_DHCP,
    Param.WIFI_IP,
    Param.WIFI_SUBNET,
    Param.WIFI_GATEWAY,
    Param.WIFI_CURRENT_IP,
]
_SENSOR_STATUS_PARAMS = [
    Param.HUMIDITY_STATUS,
    Param.VOLTAGE_STATUS,
    Param.NIGHT_TIMER,
    Param.PARTY_TIMER,
]
_ALL_PARAM_GROUPS = (_BASIC_STATUS_PARAMS, _EXTENDED_CONFIG_PARAMS, _WIFI_PARAMS, _SENSOR_STATUS_PARAMS)


def _parse_discovery_item(item: DiscoveryItem) -> DiscoveredDevice | None:
    """Parse one raw discovery response into a DiscoveredDevice, or None if malformed."""
    try:
        raw = item["raw"]
        if not isinstance(raw, (bytes, bytearray)):
            raise TypeError("Discovery item raw payload must be bytes")
        resp = parse_response(raw)
        ip_value = item["ip"]
        if not isinstance(ip_value, str):
            raise TypeError("Discovery item ip must be a string")
        return DiscoveredDevice(
            ip=ip_value,
            device_id=decode_text(resp.get(Param.DEVICE_SEARCH, b"")),
            unit_type=decode_int(resp.get(Param.UNIT_TYPE, b"\x00\x00")),
        )
    except Exception as e:
        log.warning("Discovery parse error %s: %s", item.get("ip", ""), e)
        return None


def _parse_discovery_items(items: list[DiscoveryItem]) -> list[DiscoveredDevice]:
    """Parse discovery responses and remove duplicate device advertisements."""
    devices: list[DiscoveredDevice] = []
    seen: set[str] = set()
    for item in items:
        device = _parse_discovery_item(item)
        if device is None:
            continue
        identity = device.device_id or device.ip
        if identity in seen:
            continue
        seen.add(identity)
        devices.append(device)
    return devices


class _DeviceStateBuilder:
    """Assembles a DeviceState from the raw parameter dict returned by the device."""

    def __init__(self, raw: RawParamMap, host: str) -> None:
        self._raw: RawParamMap = raw
        self._host = host

    def _int_field(self, param: Param, default: int | None = None) -> int | None:
        value = self._raw.get(param)
        return decode_int(value) if value is not None else default

    def _text_field(self, param: Param, default: str = "") -> str:
        value = self._raw.get(param)
        return decode_text(value) if value is not None else default

    def _ip_field(self, param: Param, default: str = "") -> str:
        value = self._raw.get(param)
        return decode_ip(value) if value is not None else default

    def _bool_field(self, param: Param) -> bool | None:
        """Return a boolean if the param is present, else None — avoids repeated inline ternary."""
        value = self._raw.get(param)
        return bool(decode_int(value)) if value is not None else None

    def build(self) -> DeviceState:
        state = DeviceState(ip=self._host)
        self._populate_identity(state)
        self._populate_power_and_speed(state)
        self._populate_timers(state)
        self._populate_sensors(state)
        self._populate_fan_and_filter(state)
        self._populate_maintenance(state)
        self._populate_wifi(state)
        return state

    def _populate_identity(self, state: DeviceState) -> None:
        state.device_id = self._text_field(Param.DEVICE_SEARCH)
        state.unit_type = self._int_field(Param.UNIT_TYPE) or 0

    def _populate_power_and_speed(self, state: DeviceState) -> None:
        state.power = self._bool_field(Param.POWER)
        state.speed = self._int_field(Param.SPEED)
        state.manual_speed = self._int_field(Param.MANUAL_SPEED)
        state.operation_mode = self._int_field(Param.OPERATION_MODE)
        state.boost_active = self._bool_field(Param.BOOST_STATUS)
        state.boost_delay_minutes = self._int_field(Param.BOOST_DELAY)

    def _populate_timers(self, state: DeviceState) -> None:
        state.timer_mode = self._int_field(Param.TIMER_MODE)
        if Param.TIMER_COUNTDOWN in self._raw:
            state.timer_countdown = TimerCountdown(**decode_timer_countdown(self._raw[Param.TIMER_COUNTDOWN]))
        if Param.NIGHT_TIMER in self._raw:
            v = self._raw[Param.NIGHT_TIMER]
            state.night_timer = (v[1], v[0])
        if Param.PARTY_TIMER in self._raw:
            v = self._raw[Param.PARTY_TIMER]
            state.party_timer = (v[1], v[0])

    def _populate_sensors(self, state: DeviceState) -> None:
        state.humidity_sensor = self._int_field(Param.HUMIDITY_SENSOR)
        state.humidity_threshold = self._int_field(Param.HUMIDITY_THRESHOLD)
        state.current_humidity = self._int_field(Param.CURRENT_HUMIDITY)
        state.humidity_status = self._bool_field(Param.HUMIDITY_STATUS)
        state.relay_sensor = self._int_field(Param.RELAY_SENSOR)
        state.relay_state = self._bool_field(Param.RELAY_STATE)
        state.voltage_sensor = self._int_field(Param.VOLTAGE_SENSOR)
        state.voltage_threshold = self._int_field(Param.VOLTAGE_THRESHOLD)
        state.voltage_sensor_value = self._int_field(Param.VOLTAGE_SENSOR_VAL)
        state.voltage_status = self._bool_field(Param.VOLTAGE_STATUS)

    def _populate_fan_and_filter(self, state: DeviceState) -> None:
        state.fan1_rpm = self._int_field(Param.FAN1_SPEED)
        state.fan2_rpm = self._int_field(Param.FAN2_SPEED)
        if Param.FILTER_COUNTDOWN in self._raw:
            state.filter_countdown = FilterCountdown(**decode_filter_countdown(self._raw[Param.FILTER_COUNTDOWN]))
        state.filter_needs_replacement = self._bool_field(Param.FILTER_INDICATOR)
        state.alarm_status = self._int_field(Param.ALARM_STATUS)
        if Param.MACHINE_HOURS in self._raw:
            state.machine_hours = MachineHours(**decode_machine_hours(self._raw[Param.MACHINE_HOURS]))
        state.battery_voltage_mv = self._int_field(Param.BATTERY_VOLTAGE)

    def _populate_maintenance(self, state: DeviceState) -> None:
        if Param.FIRMWARE_VERSION in self._raw:
            state.firmware = FirmwareVersion(**decode_firmware(self._raw[Param.FIRMWARE_VERSION]))
        if Param.RTC_TIME in self._raw:
            state.rtc_time = RtcTime(**decode_rtc_time(self._raw[Param.RTC_TIME]))
        if Param.RTC_CALENDAR in self._raw:
            state.rtc_calendar = RtcCalendar(**decode_rtc_calendar(self._raw[Param.RTC_CALENDAR]))
        state.weekly_schedule_enabled = self._bool_field(Param.WEEKLY_SCHEDULE_EN)
        state.cloud_permitted = self._bool_field(Param.CLOUD_PERMISSION)

    def _populate_wifi(self, state: DeviceState) -> None:
        if not any(p in self._raw for p in (Param.WIFI_MODE, Param.WIFI_SSID, Param.WIFI_IP)):
            return
        state.wifi = WifiConfig(
            mode=self._int_field(Param.WIFI_MODE, 0) or 0,
            ssid=self._text_field(Param.WIFI_SSID),
            encryption=self._int_field(Param.WIFI_ENCRYPTION, 52) or 52,
            channel=self._int_field(Param.WIFI_CHANNEL, 1) or 1,
            dhcp=bool(self._int_field(Param.WIFI_DHCP, 1)),
            ip=self._ip_field(Param.WIFI_IP),
            subnet=self._ip_field(Param.WIFI_SUBNET),
            gateway=self._ip_field(Param.WIFI_GATEWAY),
            current_ip=self._ip_field(Param.WIFI_CURRENT_IP),
        )


class VentoClient:
    def __init__(
        self,
        host: str,
        device_id: str,
        password: str = "1111",
        port: int = DEFAULT_PORT,
        timeout: float = 3.0,
    ) -> None:
        self.host = host
        self.device_id = device_id
        self.password = password
        self.port = port
        self._transport = VentoTransport(timeout=timeout)

    def _send_recv(self, packet: bytes) -> RawParamMap:
        return parse_response(self._transport.send_recv(self.host, packet, self.port))

    def _send_only(self, packet: bytes) -> None:
        self._transport.send_only(self.host, packet, self.port)

    def read_params(self, params: list[Param]) -> RawParamMap:
        return self._send_recv(build_read(self.device_id, self.password, list(params)))

    def write_params(self, param_values: ParamWriteMap) -> None:
        self._send_only(build_write(self.device_id, self.password, param_values))

    def write_params_with_response(self, param_values: ParamWriteMap) -> RawParamMap:
        return self._send_recv(build_write_resp(self.device_id, self.password, param_values))

    def increment_params(self, params: list[Param]) -> RawParamMap:
        return self._send_recv(build_increment(self.device_id, self.password, list(params)))

    def decrement_params(self, params: list[Param]) -> RawParamMap:
        return self._send_recv(build_decrement(self.device_id, self.password, list(params)))

    def get_state(self) -> DeviceState:
        combined: RawParamMap = {}
        for group in _ALL_PARAM_GROUPS:
            try:
                combined.update(self.read_params(group))
            except VentoUnsupportedParamError as e:
                log.debug("Unsupported: %s", e.params)
        return _DeviceStateBuilder(combined, self.host).build()

    def turn_on(self) -> None:
        self.write_params({Param.POWER: 1})

    def turn_off(self) -> None:
        self.write_params({Param.POWER: 0})

    def toggle_power(self) -> None:
        self.write_params({Param.POWER: 2})

    def set_speed(self, speed: int) -> None:
        _check_choices("speed", speed, {1, 2, 3})
        self.write_params({Param.SPEED: speed})

    def set_manual_speed(self, value: int) -> None:
        _check_range("manual_speed", value, 0, 255)
        self.write_params({Param.SPEED: 255, Param.MANUAL_SPEED: value})

    def speed_up(self) -> RawParamMap:
        return self.increment_params([Param.SPEED])

    def speed_down(self) -> RawParamMap:
        return self.decrement_params([Param.SPEED])

    def set_mode(self, mode: int) -> None:
        _check_choices("mode", mode, {0, 1, 2})
        self.write_params({Param.OPERATION_MODE: mode})

    def set_ventilation(self) -> None:
        self.set_mode(0)

    def set_heat_recovery(self) -> None:
        self.set_mode(1)

    def set_supply(self) -> None:
        self.set_mode(2)

    def get_boost_status(self) -> bool:
        return bool(decode_int(self.read_params([Param.BOOST_STATUS])[Param.BOOST_STATUS]))

    def set_boost_delay(self, minutes: int) -> None:
        _check_range("boost_delay", minutes, 0, 60)
        self.write_params({Param.BOOST_DELAY: minutes})

    def set_timer_mode(self, mode: int) -> None:
        _check_choices("timer_mode", mode, {0, 1, 2})
        self.write_params({Param.TIMER_MODE: mode})

    def set_night_timer(self, hours: int, minutes: int) -> None:
        _check_range("hours", hours, 0, 23)
        _check_range("minutes", minutes, 0, 59)
        self.write_params({Param.NIGHT_TIMER: bytes([minutes, hours])})

    def set_party_timer(self, hours: int, minutes: int) -> None:
        _check_range("hours", hours, 0, 23)
        _check_range("minutes", minutes, 0, 59)
        self.write_params({Param.PARTY_TIMER: bytes([minutes, hours])})

    def get_timer_countdown(self) -> TimerCountdown:
        return TimerCountdown(
            **decode_timer_countdown(self.read_params([Param.TIMER_COUNTDOWN])[Param.TIMER_COUNTDOWN])
        )

    def set_humidity_sensor(self, sensor: int) -> None:
        _check_choices("humidity_sensor", sensor, {0, 1, 2})
        self.write_params({Param.HUMIDITY_SENSOR: sensor})

    def set_humidity_threshold(self, relative_humidity: int) -> None:
        _check_range("humidity_threshold", relative_humidity, 40, 80)
        self.write_params({Param.HUMIDITY_THRESHOLD: relative_humidity})

    def get_current_humidity(self) -> int:
        return decode_int(self.read_params([Param.CURRENT_HUMIDITY])[Param.CURRENT_HUMIDITY])

    def set_relay_sensor(self, sensor: int) -> None:
        _check_choices("relay_sensor", sensor, {0, 1, 2})
        self.write_params({Param.RELAY_SENSOR: sensor})

    def set_voltage_sensor(self, sensor: int) -> None:
        _check_choices("voltage_sensor", sensor, {0, 1, 2})
        self.write_params({Param.VOLTAGE_SENSOR: sensor})

    def set_voltage_threshold(self, percent: int) -> None:
        _check_range("voltage_threshold", percent, 5, 100)
        self.write_params({Param.VOLTAGE_THRESHOLD: percent})

    def enable_weekly_schedule(self, enabled: bool) -> None:
        self.write_params({Param.WEEKLY_SCHEDULE_EN: 1 if enabled else 0})

    def set_schedule_period(self, day: int, period: int, speed: int, end_h: int, end_m: int) -> None:
        _check_range("day", day, 0, 9)
        _check_range("period", period, 1, 4)
        _check_range("speed", speed, 0, 3)
        _check_range("end_h", end_h, 0, 23)
        _check_range("end_m", end_m, 0, 59)
        self.write_params({Param.SCHEDULE_SETUP: bytes([day, period, speed, 0, end_m, end_h])})

    def get_schedule_period(self, day: int, period: int) -> SchedulePeriod:
        """Read back a single schedule period from the device.

        Reads are indexed by writing day+period as selector bytes, then
        reading the response which includes the stored speed and end time.
        """
        _check_range("day", day, 0, 9)
        _check_range("period", period, 1, 4)
        raw = self.write_params_with_response({Param.SCHEDULE_SETUP: bytes([day, period, 0, 0, 0, 0])})
        decoded = decode_schedule(raw[Param.SCHEDULE_SETUP])
        return SchedulePeriod(
            period_number=decoded["period"],
            end_hours=decoded["end_hours"],
            end_minutes=decoded["end_minutes"],
            speed=decoded["speed"],
        )

    def sync_rtc(self) -> None:
        self.set_rtc(datetime.now())

    def set_rtc(self, dt: datetime) -> None:
        day_of_week = dt.weekday() + 1
        self.write_params(
            {
                Param.RTC_TIME: bytes([dt.second, dt.minute, dt.hour]),
                Param.RTC_CALENDAR: bytes([dt.day, day_of_week, dt.month, dt.year % 100]),
            }
        )

    def get_rtc(self) -> tuple[RtcTime, RtcCalendar]:
        raw = self.read_params([Param.RTC_TIME, Param.RTC_CALENDAR])
        return (
            RtcTime(**decode_rtc_time(raw[Param.RTC_TIME])),
            RtcCalendar(**decode_rtc_calendar(raw[Param.RTC_CALENDAR])),
        )

    def get_filter_status(self) -> tuple[FilterCountdown, bool]:
        raw = self.read_params([Param.FILTER_COUNTDOWN, Param.FILTER_INDICATOR])
        return (
            FilterCountdown(**decode_filter_countdown(raw[Param.FILTER_COUNTDOWN])),
            bool(decode_int(raw[Param.FILTER_INDICATOR])),
        )

    def reset_filter_timer(self) -> None:
        self.write_params({Param.FILTER_RESET: 1})

    def get_machine_hours(self) -> MachineHours:
        return MachineHours(**decode_machine_hours(self.read_params([Param.MACHINE_HOURS])[Param.MACHINE_HOURS]))

    def reset_alarms(self) -> None:
        self.write_params({Param.RESET_ALARMS: 1})

    def get_alarm_status(self) -> int:
        return decode_int(self.read_params([Param.ALARM_STATUS])[Param.ALARM_STATUS])

    def get_firmware_version(self) -> FirmwareVersion:
        return FirmwareVersion(**decode_firmware(self.read_params([Param.FIRMWARE_VERSION])[Param.FIRMWARE_VERSION]))

    def get_unit_type(self) -> int:
        return decode_int(self.read_params([Param.UNIT_TYPE])[Param.UNIT_TYPE])

    def get_device_id(self) -> str:
        return decode_text(self.read_params([Param.DEVICE_SEARCH])[Param.DEVICE_SEARCH])

    def get_wifi_config(self) -> WifiConfig:
        raw = self.read_params(
            [
                Param.WIFI_MODE,
                Param.WIFI_SSID,
                Param.WIFI_ENCRYPTION,
                Param.WIFI_CHANNEL,
                Param.WIFI_DHCP,
                Param.WIFI_IP,
                Param.WIFI_SUBNET,
                Param.WIFI_GATEWAY,
                Param.WIFI_CURRENT_IP,
            ]
        )
        return WifiConfig(
            mode=decode_int(raw.get(Param.WIFI_MODE, b"\x01")),
            ssid=decode_text(raw.get(Param.WIFI_SSID, b"")),
            encryption=decode_int(raw.get(Param.WIFI_ENCRYPTION, b"4")),
            channel=decode_int(raw.get(Param.WIFI_CHANNEL, b"\x06")),
            dhcp=bool(decode_int(raw.get(Param.WIFI_DHCP, b"\x01"))),
            ip=decode_ip(raw.get(Param.WIFI_IP, bytes(4))),
            subnet=decode_ip(raw.get(Param.WIFI_SUBNET, bytes(4))),
            gateway=decode_ip(raw.get(Param.WIFI_GATEWAY, bytes(4))),
            current_ip=decode_ip(raw.get(Param.WIFI_CURRENT_IP, bytes(4))),
        )

    def set_wifi_client(
        self,
        ssid: str,
        wifi_password: str,
        dhcp: bool = True,
        encryption: int = 52,
        static_ip: str = "",
        subnet: str = "",
        gateway: str = "",
    ) -> None:
        params: ParamWriteMap = {
            Param.WIFI_MODE: 1,
            Param.WIFI_SSID: ssid.encode("ascii"),
            Param.WIFI_PASSWORD: wifi_password.encode("ascii"),
            Param.WIFI_ENCRYPTION: encryption,
            Param.WIFI_DHCP: 1 if dhcp else 0,
        }
        if not dhcp:
            if not static_ip:
                raise VentoValueError("static_ip required when dhcp=False")
            params[Param.WIFI_IP] = encode_ip(static_ip)
            params[Param.WIFI_SUBNET] = encode_ip(subnet or "255.255.255.0")
            params[Param.WIFI_GATEWAY] = encode_ip(gateway or static_ip)
        self.write_params(params)

    def set_wifi_ap(self, channel: int = 6) -> None:
        _check_range("channel", channel, 1, 13)
        self.write_params({Param.WIFI_MODE: 2, Param.WIFI_CHANNEL: channel})

    def apply_wifi_config(self) -> None:
        self.write_params({Param.WIFI_APPLY: 1})

    def discard_wifi_config(self) -> None:
        self.write_params({Param.WIFI_DISCARD: 1})

    def change_password(self, password: str) -> None:
        if len(password) > 8:
            raise VentoValueError("Password max 8 characters")
        self.write_params({Param.DEVICE_PASSWORD: password.encode("ascii")})
        self.password = password

    def set_cloud_permission(self, allowed: bool) -> None:
        self.write_params({Param.CLOUD_PERMISSION: 1 if allowed else 0})

    def factory_reset(self) -> None:
        self.write_params({Param.FACTORY_RESET: 1})

    @staticmethod
    def discover(
        broadcast: str = "255.255.255.255",
        port: int = DEFAULT_PORT,
        timeout: float = 3.0,
    ) -> list[DiscoveredDevice]:
        transport = VentoTransport(timeout=timeout)
        raw_items = transport.discover(build_discovery(), broadcast, port, timeout)
        return _parse_discovery_items(raw_items)

    def __repr__(self) -> str:
        return f"<VentoClient host={self.host!r} id={self.device_id!r}>"


class AsyncVentoClient:
    def __init__(
        self,
        host: str,
        device_id: str,
        password: str = "1111",
        port: int = DEFAULT_PORT,
        timeout: float = 3.0,
    ) -> None:
        self.host = host
        self.device_id = device_id
        self.password = password
        self.port = port
        self._transport = AsyncVentoTransport(timeout=timeout)

    async def __aenter__(self) -> AsyncVentoClient:
        return self

    async def __aexit__(self, *_) -> None:
        pass

    async def _send_recv(self, packet: bytes) -> RawParamMap:
        return parse_response(await self._transport.send_recv(self.host, packet, self.port))

    async def _send_only(self, packet: bytes) -> None:
        await self._transport.send_only(self.host, packet, self.port)

    async def read_params(self, params: list[Param]) -> RawParamMap:
        return await self._send_recv(build_read(self.device_id, self.password, list(params)))

    async def write_params(self, param_values: ParamWriteMap) -> None:
        await self._send_only(build_write(self.device_id, self.password, param_values))

    async def write_params_with_response(self, param_values: ParamWriteMap) -> RawParamMap:
        return await self._send_recv(build_write_resp(self.device_id, self.password, param_values))

    async def get_state(self) -> DeviceState:
        combined: RawParamMap = {}
        for group in _ALL_PARAM_GROUPS:
            try:
                combined.update(await self.read_params(group))
            except VentoUnsupportedParamError as e:
                log.debug("Unsupported: %s", e.params)
        return _DeviceStateBuilder(combined, self.host).build()

    async def turn_on(self) -> None:
        await self.write_params({Param.POWER: 1})

    async def turn_off(self) -> None:
        await self.write_params({Param.POWER: 0})

    async def toggle_power(self) -> None:
        await self.write_params({Param.POWER: 2})

    async def set_speed(self, speed: int) -> None:
        _check_choices("speed", speed, {1, 2, 3})
        await self.write_params({Param.SPEED: speed})

    async def set_manual_speed(self, value: int) -> None:
        _check_range("manual_speed", value, 0, 255)
        await self.write_params({Param.SPEED: 255, Param.MANUAL_SPEED: value})

    async def set_mode(self, mode: int) -> None:
        _check_choices("mode", mode, {0, 1, 2})
        await self.write_params({Param.OPERATION_MODE: mode})

    async def set_ventilation(self) -> None:
        await self.set_mode(0)

    async def set_heat_recovery(self) -> None:
        await self.set_mode(1)

    async def set_supply(self) -> None:
        await self.set_mode(2)

    async def set_timer_mode(self, mode: int) -> None:
        _check_choices("timer_mode", mode, {0, 1, 2})
        await self.write_params({Param.TIMER_MODE: mode})

    async def set_night_timer(self, hours: int, minutes: int) -> None:
        _check_range("hours", hours, 0, 23)
        _check_range("minutes", minutes, 0, 59)
        await self.write_params({Param.NIGHT_TIMER: bytes([minutes, hours])})

    async def set_party_timer(self, hours: int, minutes: int) -> None:
        _check_range("hours", hours, 0, 23)
        _check_range("minutes", minutes, 0, 59)
        await self.write_params({Param.PARTY_TIMER: bytes([minutes, hours])})

    async def set_humidity_sensor(self, sensor: int) -> None:
        _check_choices("humidity_sensor", sensor, {0, 1, 2})
        await self.write_params({Param.HUMIDITY_SENSOR: sensor})

    async def set_humidity_threshold(self, relative_humidity: int) -> None:
        _check_range("humidity_threshold", relative_humidity, 40, 80)
        await self.write_params({Param.HUMIDITY_THRESHOLD: relative_humidity})

    async def set_relay_sensor(self, sensor: int) -> None:
        _check_choices("relay_sensor", sensor, {0, 1, 2})
        await self.write_params({Param.RELAY_SENSOR: sensor})

    async def set_voltage_sensor(self, sensor: int) -> None:
        _check_choices("voltage_sensor", sensor, {0, 1, 2})
        await self.write_params({Param.VOLTAGE_SENSOR: sensor})

    async def set_voltage_threshold(self, percent: int) -> None:
        _check_range("voltage_threshold", percent, 5, 100)
        await self.write_params({Param.VOLTAGE_THRESHOLD: percent})

    async def enable_weekly_schedule(self, enabled: bool) -> None:
        await self.write_params({Param.WEEKLY_SCHEDULE_EN: 1 if enabled else 0})

    async def set_schedule_period(self, day: int, period: int, speed: int, end_h: int, end_m: int) -> None:
        _check_range("day", day, 0, 9)
        _check_range("period", period, 1, 4)
        _check_range("speed", speed, 0, 3)
        _check_range("end_h", end_h, 0, 23)
        _check_range("end_m", end_m, 0, 59)
        await self.write_params({Param.SCHEDULE_SETUP: bytes([day, period, speed, 0, end_m, end_h])})

    async def get_schedule_period(self, day: int, period: int) -> SchedulePeriod:
        """Read back a single schedule period from the device."""
        _check_range("day", day, 0, 9)
        _check_range("period", period, 1, 4)
        raw = await self.write_params_with_response({Param.SCHEDULE_SETUP: bytes([day, period, 0, 0, 0, 0])})
        decoded = decode_schedule(raw[Param.SCHEDULE_SETUP])
        return SchedulePeriod(
            period_number=decoded["period"],
            end_hours=decoded["end_hours"],
            end_minutes=decoded["end_minutes"],
            speed=decoded["speed"],
        )

    async def set_boost_delay(self, minutes: int) -> None:
        _check_range("boost_delay", minutes, 0, 60)
        await self.write_params({Param.BOOST_DELAY: minutes})

    async def reset_filter_timer(self) -> None:
        await self.write_params({Param.FILTER_RESET: 1})

    async def reset_alarms(self) -> None:
        await self.write_params({Param.RESET_ALARMS: 1})

    async def sync_rtc(self) -> None:
        await self.set_rtc(datetime.now())

    async def set_rtc(self, dt: datetime) -> None:
        day_of_week = dt.weekday() + 1
        await self.write_params(
            {
                Param.RTC_TIME: bytes([dt.second, dt.minute, dt.hour]),
                Param.RTC_CALENDAR: bytes([dt.day, day_of_week, dt.month, dt.year % 100]),
            }
        )

    async def factory_reset(self) -> None:
        await self.write_params({Param.FACTORY_RESET: 1})

    async def change_password(self, password: str) -> None:
        if len(password) > 8:
            raise VentoValueError("Password max 8 characters")
        await self.write_params({Param.DEVICE_PASSWORD: password.encode("ascii")})
        self.password = password

    async def set_cloud_permission(self, allowed: bool) -> None:
        await self.write_params({Param.CLOUD_PERMISSION: 1 if allowed else 0})

    @staticmethod
    async def discover(
        broadcast: str = "255.255.255.255",
        port: int = DEFAULT_PORT,
        timeout: float = 3.0,
    ) -> list[DiscoveredDevice]:
        transport = AsyncVentoTransport(timeout=timeout)
        raw_items = await transport.discover(build_discovery(), broadcast, port, timeout)
        return _parse_discovery_items(raw_items)

    def __repr__(self) -> str:
        return f"<AsyncVentoClient host={self.host!r} id={self.device_id!r}>"
