import asyncio
import socket
from unittest.mock import MagicMock, patch

import pytest
from blauberg_vento.exceptions import VentoConnectionError, VentoTimeoutError
from blauberg_vento.transport import AsyncVentoTransport, VentoTransport


def test_sync_send_recv_raises_timeout_error() -> None:
    fake_socket = MagicMock()
    fake_socket.__enter__.return_value = fake_socket
    fake_socket.recvfrom.side_effect = TimeoutError()

    with patch("blauberg_vento.transport.socket.socket", return_value=fake_socket):
        with pytest.raises(VentoTimeoutError):
            VentoTransport(timeout=0.01).send_recv("127.0.0.1", b"packet")


@pytest.mark.asyncio
async def test_async_send_recv_raises_timeout_error() -> None:
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    port = receiver.getsockname()[1]
    try:
        with pytest.raises(VentoTimeoutError):
            await AsyncVentoTransport(timeout=0.01).send_recv("127.0.0.1", b"packet", port)
    finally:
        receiver.close()


@pytest.mark.asyncio
async def test_async_send_only_wraps_socket_creation_error() -> None:
    loop = asyncio.get_running_loop()
    with patch.object(
        loop,
        "create_datagram_endpoint",
        side_effect=OSError("socket unavailable"),
    ):
        with pytest.raises(VentoConnectionError, match="Cannot open socket"):
            await AsyncVentoTransport().send_only("127.0.0.1", b"packet")
