from unittest.mock import patch

from blauberg_vento.client import VentoClient, _parse_discovery_items
from blauberg_vento.models import DiscoveredDevice


def test_parse_discovery_items_deduplicates_device_advertisements() -> None:
    device = DiscoveredDevice(ip="192.0.2.10", device_id="FAN-01", unit_type=3)

    with patch("blauberg_vento.client._parse_discovery_item", return_value=device):
        result = _parse_discovery_items(
            [
                {"ip": "192.0.2.10", "raw": b"first"},
                {"ip": "192.0.2.10", "raw": b"duplicate"},
            ]
        )

    assert result == [device]


def test_discover_returns_unique_devices() -> None:
    device = DiscoveredDevice(ip="192.0.2.10", device_id="FAN-01", unit_type=3)
    with patch("blauberg_vento.client.VentoTransport") as transport_type:
        transport_type.return_value.discover.return_value = [
            {"ip": "192.0.2.10", "raw": b"first"},
            {"ip": "192.0.2.10", "raw": b"duplicate"},
        ]
        with patch("blauberg_vento.client._parse_discovery_item", return_value=device):
            result = VentoClient.discover()

    assert result == [device]
