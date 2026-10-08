from importlib.metadata import PackageNotFoundError, version

from .client import AsyncVentoClient, VentoClient
from .exceptions import (
    VentoAuthError,
    VentoChecksumError,
    VentoConnectionError,
    VentoDiscoveryError,
    VentoError,
    VentoInvalidResponseError,
    VentoProtocolError,
    VentoTimeoutError,
    VentoUnsupportedParamError,
    VentoValueError,
)
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
from .parameters import Func, Param

try:
    __version__ = version("blauberg-vento")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = [
    "VentoClient",
    "AsyncVentoClient",
    "DeviceState",
    "DiscoveredDevice",
    "FilterCountdown",
    "FirmwareVersion",
    "MachineHours",
    "RtcCalendar",
    "RtcTime",
    "SchedulePeriod",
    "TimerCountdown",
    "WifiConfig",
    "Param",
    "Func",
    "VentoError",
    "VentoConnectionError",
    "VentoTimeoutError",
    "VentoChecksumError",
    "VentoProtocolError",
    "VentoInvalidResponseError",
    "VentoAuthError",
    "VentoUnsupportedParamError",
    "VentoValueError",
    "VentoDiscoveryError",
]
