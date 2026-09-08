"""
Blauberg Vento Protocol Parameters

This module defines:
- `Param`: Enum of all supported Blauberg Vento protocol parameters (e.g., `POWER`, `SPEED`, `HUMIDITY_SENSOR`).
- `Func`: Enum of protocol functions (e.g., `READ`, `WRITE`, `INCREMENT`).
- `PARAM_META`: Metadata for each parameter, including:
  - Supported functions (`func`).
  - Size in bytes (`size`).
  - Whether the parameter is unsupported on A30 units (`not_a30`).
  - Human-readable description (`desc`).
  - Valid values or ranges (`values`, `range`).

Helper Functions:
- `is_readable(param)`: Check if a parameter can be read.
- `is_writable(param)`: Check if a parameter can be written.
- `param_size(param)`: Get the size of a parameter in bytes.

Usage Example:
    from parameters import Param, is_readable
    if is_readable(Param.POWER):
        print("POWER can be read from the device.")
"""
from enum import IntEnum
from typing import TypedDict


class Func(IntEnum):
    READ = 0x01
    WRITE = 0x02
    WRITE_RESP = 0x03
    INCREMENT = 0x04
    DECREMENT = 0x05
    RESPONSE = 0x06


CMD_PAGE = 0xFF
CMD_FUNC = 0xFC
CMD_SIZE = 0xFE
CMD_NOT_SUP = 0xFD

PACKET_START = bytes([0xFD, 0xFD])
PROTOCOL_TYPE = 0x02

DEFAULT_DEVICE_ID = b"DEFAULT_DEVICEID"
DEFAULT_PORT = 4000
MAX_PACKET_SIZE = 256


class Param(IntEnum):
    POWER = 0x0001
    SPEED = 0x0002
    BOOST_STATUS = 0x0006
    TIMER_MODE = 0x0007
    TIMER_COUNTDOWN = 0x000B
    HUMIDITY_SENSOR = 0x000F
    RELAY_SENSOR = 0x0014
    VOLTAGE_SENSOR = 0x0016
    HUMIDITY_THRESHOLD = 0x0019
    VOLTAGE_THRESHOLD = 0x00B8
    BATTERY_VOLTAGE = 0x0024
    CURRENT_HUMIDITY = 0x0025
    VOLTAGE_SENSOR_VAL = 0x002D
    RELAY_STATE = 0x0032
    HUMIDITY_STATUS = 0x0304
    VOLTAGE_STATUS = 0x0305
    MANUAL_SPEED = 0x0044
    FAN1_SPEED = 0x004A
    FAN2_SPEED = 0x004B
    FILTER_COUNTDOWN = 0x0064
    FILTER_RESET = 0x0065
    FILTER_INDICATOR = 0x0088
    BOOST_DELAY = 0x0066
    RTC_TIME = 0x006F
    RTC_CALENDAR = 0x0070
    WEEKLY_SCHEDULE_EN = 0x0072
    SCHEDULE_SETUP = 0x0077
    DEVICE_SEARCH = 0x007C
    DEVICE_PASSWORD = 0x007D
    MACHINE_HOURS = 0x007E
    RESET_ALARMS = 0x0080
    ALARM_STATUS = 0x0083
    CLOUD_PERMISSION = 0x0085
    FIRMWARE_VERSION = 0x0086
    FACTORY_RESET = 0x0087
    WIFI_MODE = 0x0094
    WIFI_SSID = 0x0095
    WIFI_PASSWORD = 0x0096
    WIFI_ENCRYPTION = 0x0099
    WIFI_CHANNEL = 0x009A
    WIFI_DHCP = 0x009B
    WIFI_IP = 0x009C
    WIFI_SUBNET = 0x009D
    WIFI_GATEWAY = 0x009E
    WIFI_APPLY = 0x00A0
    WIFI_DISCARD = 0x00A2
    WIFI_CURRENT_IP = 0x00A3
    OPERATION_MODE = 0x00B7
    UNIT_TYPE = 0x00B9
    NIGHT_TIMER = 0x0302
    PARTY_TIMER = 0x0303


class ParamMeta(TypedDict):
    func: frozenset[str]
    size: int | None
    not_a30: bool
    desc: str
    values: dict[int, str] | None
    range: tuple[int, int] | None


_READ_ONLY = frozenset(["R"])
_WRITE_ONLY = frozenset(["W"])
_READ_WRITE = frozenset(["R", "W", "RW"])
_READ_WRITE_INC_DEC = frozenset(["R", "W", "RW", "INC", "DEC"])

PARAM_META: dict[Param, ParamMeta] = {
    Param.POWER: {
        "func": _READ_WRITE,
        "size": 1,
        "not_a30": False,
        "desc": "Unit On/Off",
        "values": {0: "Off", 1: "On", 2: "Invert"},
        "range": None,
    },
    Param.SPEED: {
        "func": _READ_WRITE_INC_DEC,
        "size": 1,
        "not_a30": False,
        "desc": "Speed number",
        "values": {1: "Speed 1", 2: "Speed 2", 3: "Speed 3", 255: "Manual"},
        "range": None,
    },
    Param.BOOST_STATUS: {
        "func": _READ_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Boost status",
        "values": {0: "Off", 1: "On"},
        "range": None,
    },
    Param.TIMER_MODE: {
        "func": _READ_WRITE_INC_DEC,
        "size": 1,
        "not_a30": False,
        "desc": "Timer mode",
        "values": {0: "Off", 1: "Night", 2: "Party"},
        "range": None,
    },
    Param.TIMER_COUNTDOWN: {
        "func": _READ_ONLY,
        "size": 3,
        "not_a30": False,
        "desc": "Timer countdown",
        "values": None,
        "range": None,
    },
    Param.HUMIDITY_SENSOR: {
        "func": _READ_WRITE,
        "size": 1,
        "not_a30": False,
        "desc": "Humidity sensor",
        "values": {0: "Off", 1: "On", 2: "Invert"},
        "range": None,
    },
    Param.RELAY_SENSOR: {
        "func": _READ_WRITE,
        "size": 1,
        "not_a30": False,
        "desc": "Relay sensor",
        "values": {0: "Off", 1: "On", 2: "Invert"},
        "range": None,
    },
    Param.VOLTAGE_SENSOR: {
        "func": _READ_WRITE,
        "size": 1,
        "not_a30": True,
        "desc": "0-10V sensor",
        "values": {0: "Off", 1: "On", 2: "Invert"},
        "range": None,
    },
    Param.HUMIDITY_THRESHOLD: {
        "func": _READ_WRITE_INC_DEC,
        "size": 1,
        "not_a30": False,
        "desc": "Humidity threshold (%RH)",
        "values": None,
        "range": (40, 80),
    },
    Param.VOLTAGE_THRESHOLD: {
        "func": _READ_WRITE_INC_DEC,
        "size": 1,
        "not_a30": True,
        "desc": "0-10V threshold (%)",
        "values": None,
        "range": (5, 100),
    },
    Param.BATTERY_VOLTAGE: {
        "func": _READ_ONLY,
        "size": 2,
        "not_a30": False,
        "desc": "Battery voltage (mV)",
        "values": None,
        "range": (0, 5000),
    },
    Param.CURRENT_HUMIDITY: {
        "func": _READ_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Current humidity (%RH)",
        "values": None,
        "range": (0, 100),
    },
    Param.VOLTAGE_SENSOR_VAL: {
        "func": _READ_ONLY,
        "size": 1,
        "not_a30": True,
        "desc": "0-10V value (%)",
        "values": None,
        "range": (0, 100),
    },
    Param.RELAY_STATE: {
        "func": _READ_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Relay state",
        "values": {0: "Off", 1: "On"},
        "range": None,
    },
    Param.HUMIDITY_STATUS: {
        "func": _READ_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Humidity status",
        "values": {0: "Below", 1: "Over"},
        "range": None,
    },
    Param.VOLTAGE_STATUS: {
        "func": _READ_ONLY,
        "size": 1,
        "not_a30": True,
        "desc": "0-10V status",
        "values": {0: "Below", 1: "Over"},
        "range": None,
    },
    Param.MANUAL_SPEED: {
        "func": _READ_WRITE_INC_DEC,
        "size": 1,
        "not_a30": False,
        "desc": "Manual speed (0-255)",
        "values": None,
        "range": (0, 255),
    },
    Param.FAN1_SPEED: {
        "func": _READ_ONLY,
        "size": 2,
        "not_a30": False,
        "desc": "Fan 1 speed (rpm)",
        "values": None,
        "range": (0, 5000),
    },
    Param.FAN2_SPEED: {
        "func": _READ_ONLY,
        "size": 2,
        "not_a30": False,
        "desc": "Fan 2 speed (rpm)",
        "values": None,
        "range": (0, 5000),
    },
    Param.FILTER_COUNTDOWN: {
        "func": _READ_ONLY,
        "size": 3,
        "not_a30": False,
        "desc": "Filter countdown",
        "values": None,
        "range": None,
    },
    Param.FILTER_RESET: {
        "func": _WRITE_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Reset filter timer",
        "values": None,
        "range": None,
    },
    Param.FILTER_INDICATOR: {
        "func": _READ_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Filter indicator",
        "values": {0: "OK", 1: "Replace"},
        "range": None,
    },
    Param.BOOST_DELAY: {
        "func": _READ_WRITE_INC_DEC,
        "size": 1,
        "not_a30": False,
        "desc": "Boost delay (0-60 min)",
        "values": None,
        "range": (0, 60),
    },
    Param.RTC_TIME: {
        "func": _READ_WRITE,
        "size": 3,
        "not_a30": False,
        "desc": "RTC time",
        "values": None,
        "range": None,
    },
    Param.RTC_CALENDAR: {
        "func": _READ_WRITE,
        "size": 4,
        "not_a30": False,
        "desc": "RTC calendar",
        "values": None,
        "range": None,
    },
    Param.WEEKLY_SCHEDULE_EN: {
        "func": _READ_WRITE,
        "size": 1,
        "not_a30": False,
        "desc": "Weekly schedule",
        "values": {0: "Off", 1: "On", 2: "Invert"},
        "range": None,
    },
    Param.SCHEDULE_SETUP: {
        "func": _READ_WRITE,
        "size": 6,
        "not_a30": False,
        "desc": "Schedule setup",
        "values": None,
        "range": None,
    },
    Param.DEVICE_SEARCH: {
        "func": _READ_ONLY,
        "size": 16,
        "not_a30": False,
        "desc": "Device search/ID",
        "values": None,
        "range": None,
    },
    Param.DEVICE_PASSWORD: {
        "func": _READ_WRITE,
        "size": None,
        "not_a30": False,
        "desc": "Device password",
        "values": None,
        "range": None,
    },
    Param.MACHINE_HOURS: {
        "func": _READ_ONLY,
        "size": 4,
        "not_a30": False,
        "desc": "Machine hours",
        "values": None,
        "range": None,
    },
    Param.RESET_ALARMS: {
        "func": _WRITE_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Reset alarms",
        "values": None,
        "range": None,
    },
    Param.ALARM_STATUS: {
        "func": _READ_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Alarm status",
        "values": {0: "No alarm", 1: "Alarm", 2: "Warning"},
        "range": None,
    },
    Param.CLOUD_PERMISSION: {
        "func": _READ_WRITE,
        "size": 1,
        "not_a30": False,
        "desc": "Cloud permission",
        "values": {0: "Off", 1: "On", 2: "Invert"},
        "range": None,
    },
    Param.FIRMWARE_VERSION: {
        "func": _READ_ONLY,
        "size": 6,
        "not_a30": False,
        "desc": "Firmware version",
        "values": None,
        "range": None,
    },
    Param.FACTORY_RESET: {
        "func": _WRITE_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Factory reset",
        "values": None,
        "range": None,
    },
    Param.WIFI_MODE: {
        "func": _READ_WRITE_INC_DEC,
        "size": 1,
        "not_a30": False,
        "desc": "Wi-Fi mode",
        "values": {1: "Client", 2: "AP"},
        "range": None,
    },
    Param.WIFI_SSID: {
        "func": _READ_WRITE,
        "size": None,
        "not_a30": False,
        "desc": "Wi-Fi SSID",
        "values": None,
        "range": None,
    },
    Param.WIFI_PASSWORD: {
        "func": _READ_WRITE,
        "size": None,
        "not_a30": False,
        "desc": "Wi-Fi password",
        "values": None,
        "range": None,
    },
    Param.WIFI_ENCRYPTION: {
        "func": _READ_WRITE,
        "size": 1,
        "not_a30": False,
        "desc": "Wi-Fi encryption",
        "values": {48: "OPEN", 50: "WPA_PSK", 51: "WPA2_PSK", 52: "WPA_WPA2_PSK"},
        "range": None,
    },
    Param.WIFI_CHANNEL: {
        "func": _READ_WRITE_INC_DEC,
        "size": 1,
        "not_a30": False,
        "desc": "Wi-Fi channel",
        "values": None,
        "range": (1, 13),
    },
    Param.WIFI_DHCP: {
        "func": _READ_WRITE,
        "size": 1,
        "not_a30": False,
        "desc": "Wi-Fi DHCP",
        "values": {0: "Static", 1: "DHCP", 2: "Invert"},
        "range": None,
    },
    Param.WIFI_IP: {
        "func": _READ_WRITE,
        "size": 4,
        "not_a30": False,
        "desc": "Wi-Fi IP",
        "values": None,
        "range": None,
    },
    Param.WIFI_SUBNET: {
        "func": _READ_WRITE,
        "size": 4,
        "not_a30": False,
        "desc": "Wi-Fi subnet",
        "values": None,
        "range": None,
    },
    Param.WIFI_GATEWAY: {
        "func": _READ_WRITE,
        "size": 4,
        "not_a30": False,
        "desc": "Wi-Fi gateway",
        "values": None,
        "range": None,
    },
    Param.WIFI_APPLY: {
        "func": _WRITE_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Apply Wi-Fi config",
        "values": None,
        "range": None,
    },
    Param.WIFI_DISCARD: {
        "func": _WRITE_ONLY,
        "size": 1,
        "not_a30": False,
        "desc": "Discard Wi-Fi config",
        "values": None,
        "range": None,
    },
    Param.WIFI_CURRENT_IP: {
        "func": _READ_ONLY,
        "size": 4,
        "not_a30": False,
        "desc": "Current Wi-Fi IP",
        "values": None,
        "range": None,
    },
    Param.OPERATION_MODE: {
        "func": _READ_WRITE_INC_DEC,
        "size": 1,
        "not_a30": False,
        "desc": "Operation mode",
        "values": {0: "Ventilation", 1: "Heat Recovery", 2: "Supply"},
        "range": None,
    },
    Param.UNIT_TYPE: {
        "func": _READ_ONLY,
        "size": 2,
        "not_a30": False,
        "desc": "Unit type",
        "values": {3: "A50/A85/A100 V.2", 4: "Duo A30 V.2", 5: "A30 V.2"},
        "range": None,
    },
    Param.NIGHT_TIMER: {
        "func": _READ_WRITE,
        "size": 2,
        "not_a30": False,
        "desc": "Night timer",
        "values": None,
        "range": None,
    },
    Param.PARTY_TIMER: {
        "func": _READ_WRITE,
        "size": 2,
        "not_a30": False,
        "desc": "Party timer",
        "values": None,
        "range": None,
    },
}


def param_size(p: Param) -> int | None:
    return PARAM_META[p]["size"]


def is_readable(p: Param) -> bool:
    return "R" in PARAM_META[p]["func"]


def is_writable(p: Param) -> bool:
    return "W" in PARAM_META[p]["func"] or "RW" in PARAM_META[p]["func"]


def is_incrementable(p: Param) -> bool:
    return "INC" in PARAM_META[p]["func"]


def is_not_a30(p: Param) -> bool:
    return PARAM_META[p]["not_a30"]
