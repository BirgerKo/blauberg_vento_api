"""
Blauberg Vento Data Models

This module defines dataclasses and named tuples to represent:
- Device state (`DeviceState`): Current status of a Vento device (e.g., power, speed, sensors).
- Configuration models (`FirmwareVersion`, `WifiConfig`, `RtcTime`, etc.).
- Unit type metadata (`_UNIT_TYPE_INFO`): Maps unit type IDs to human-readable names.

Key Classes:
- `DeviceState`: Aggregates all readable parameters from a device.
- `DiscoveredDevice`: Represents a device found during UDP discovery.
- `FirmwareVersion`, `RtcTime`, `RtcCalendar`: Structured representations of device metadata.

Usage Example:
    state = client.get_state()
    print(f"Device: {state.device_id}, Power: {'ON' if state.power else 'OFF'}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

_DAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_SCHEDULE_SPEED_NAMES = ["Standby", "Speed 1", "Speed 2", "Speed 3"]

TimerTuple = tuple[int, int]


@dataclass
class FirmwareVersion:
    major: int
    minor: int
    day: int
    month: int
    year: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor} ({self.year}-{self.month:02d}-{self.day:02d})"


@dataclass
class RtcTime:
    hours: int
    minutes: int
    seconds: int

    def __str__(self) -> str:
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}"


@dataclass
class RtcCalendar:
    year: int
    month: int
    day: int
    day_of_week: int

    def __str__(self) -> str:
        dow = _DAY_ABBREVIATIONS[self.day_of_week - 1] if 1 <= self.day_of_week <= 7 else "?"
        return f"{self.year}-{self.month:02d}-{self.day:02d} ({dow})"


@dataclass
class TimerCountdown:
    hours: int
    minutes: int
    seconds: int

    def total_seconds(self) -> int:
        return self.hours * 3600 + self.minutes * 60 + self.seconds

    def __str__(self) -> str:
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}"


@dataclass
class FilterCountdown:
    days: int
    hours: int
    minutes: int

    def __str__(self) -> str:
        return f"{self.days}d {self.hours:02d}h {self.minutes:02d}m"


@dataclass
class MachineHours:
    days: int
    hours: int
    minutes: int

    def total_hours(self) -> float:
        return self.days * 24 + self.hours + self.minutes / 60

    def __str__(self) -> str:
        return f"{self.days}d {self.hours:02d}h {self.minutes:02d}m"


@dataclass
class SchedulePeriod:
    period_number: int
    end_hours: int
    end_minutes: int
    speed: int

    def __str__(self) -> str:
        speed_name = _SCHEDULE_SPEED_NAMES[self.speed] if 0 <= self.speed <= 3 else str(self.speed)
        return f"Period {self.period_number}: -> {self.end_hours:02d}:{self.end_minutes:02d} @ {speed_name}"


ScheduleKey = tuple[int, int]
ScheduleMap = dict[ScheduleKey, SchedulePeriod]


@dataclass
class WifiConfig:
    mode: int
    ssid: str
    encryption: int
    channel: int
    dhcp: bool
    ip: str
    subnet: str
    gateway: str
    current_ip: str

    @property
    def mode_name(self) -> str:
        return {1: "Client", 2: "Access Point"}.get(self.mode, "Unknown")

    @property
    def encryption_name(self) -> str:
        return {48: "OPEN", 50: "WPA_PSK", 51: "WPA2_PSK", 52: "WPA_WPA2_PSK"}.get(self.encryption, "Unknown")


class _UnitTypeInfo(NamedTuple):
    name: str
    is_a30: bool


# Single source of truth for unit type metadata — add new models here only
_UNIT_TYPE_INFO: dict[int, _UnitTypeInfo] = {
    3: _UnitTypeInfo("Vento Expert A50-1/A85-1/A100-1 W V.2", is_a30=False),
    4: _UnitTypeInfo("Vento Expert Duo A30-1 W V.2", is_a30=False),
    5: _UnitTypeInfo("Vento Expert A30 W V.2", is_a30=True),
}

# Backward-compatible aliases kept for external consumers
UNIT_TYPE_NAMES = {k: v.name for k, v in _UNIT_TYPE_INFO.items()}
UNIT_TYPE_IS_A30 = {k: v.is_a30 for k, v in _UNIT_TYPE_INFO.items()}


@dataclass
class DeviceState:
    ip: str = ""
    device_id: str = ""
    unit_type: int = 0
    power: bool | None = None
    speed: int | None = None
    manual_speed: int | None = None
    operation_mode: int | None = None
    boost_active: bool | None = None
    boost_delay_minutes: int | None = None
    timer_mode: int | None = None
    timer_countdown: TimerCountdown | None = None
    night_timer: TimerTuple | None = None
    party_timer: TimerTuple | None = None
    humidity_sensor: int | None = None
    humidity_threshold: int | None = None
    current_humidity: int | None = None
    humidity_status: bool | None = None
    relay_sensor: int | None = None
    relay_state: bool | None = None
    voltage_sensor: int | None = None
    voltage_threshold: int | None = None
    voltage_sensor_value: int | None = None
    voltage_status: bool | None = None
    fan1_rpm: int | None = None
    fan2_rpm: int | None = None
    filter_countdown: FilterCountdown | None = None
    filter_needs_replacement: bool | None = None
    alarm_status: int | None = None
    machine_hours: MachineHours | None = None
    battery_voltage_mv: int | None = None
    firmware: FirmwareVersion | None = None
    rtc_time: RtcTime | None = None
    rtc_calendar: RtcCalendar | None = None
    weekly_schedule_enabled: bool | None = None
    schedule: ScheduleMap = field(default_factory=lambda: {})
    wifi: WifiConfig | None = None
    cloud_permitted: bool | None = None

    @property
    def unit_type_name(self) -> str:
        info = _UNIT_TYPE_INFO.get(self.unit_type or 0)
        return info.name if info else f"Unknown ({self.unit_type})"

    @property
    def is_a30(self) -> bool:
        info = _UNIT_TYPE_INFO.get(self.unit_type or 0)
        return info.is_a30 if info else False

    @property
    def operation_mode_name(self) -> str:
        mode = self.operation_mode if self.operation_mode is not None else 0
        return {0: "Ventilation", 1: "Heat Recovery", 2: "Supply"}.get(mode, "Unknown")

    @property
    def speed_name(self) -> str:
        speed = self.speed if self.speed is not None else 0
        if speed == 255:
            manual_speed = self.manual_speed if self.manual_speed is not None else 0
            return f"Manual ({manual_speed})"
        return {1: "Speed 1", 2: "Speed 2", 3: "Speed 3"}.get(speed, "Unknown")

    @property
    def alarm_name(self) -> str:
        status = self.alarm_status if self.alarm_status is not None else -1
        return {0: "OK", 1: "Alarm", 2: "Warning"}.get(status, "Unknown")

    def __repr__(self) -> str:
        return (
            f"<DeviceState ip={self.ip!r} id={self.device_id!r} type={self.unit_type_name!r} "
            f"power={'ON' if self.power else 'OFF'} speed={self.speed_name} mode={self.operation_mode_name}>"
        )


@dataclass
class DiscoveredDevice:
    ip: str
    device_id: str
    unit_type: int
    unit_type_name: str = ""

    def __post_init__(self) -> None:
        if not self.unit_type_name:
            info = _UNIT_TYPE_INFO.get(self.unit_type)
            self.unit_type_name = info.name if info else f"Unknown ({self.unit_type})"

    def __repr__(self) -> str:
        return f"<DiscoveredDevice ip={self.ip!r} id={self.device_id!r} type={self.unit_type_name!r}>"
