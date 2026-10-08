"""Tests for ack-robustness in the transport layer.

Target contract (TDD):
- A datagram from a source address other than the target host is ignored:
  the transport keeps waiting for the right source until timeout.
- The asyncio single-response protocol takes an optional expected host and
  only resolves its future for datagrams from that host. Without an expected
  host it accepts any source (backward compatible).
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from blauberg_vento.exceptions import VentoTimeoutError
from blauberg_vento.transport import AsyncVentoTransport, VentoTransport, _SingleResponseProtocol

HOST = "192.0.2.10"
FOREIGN = "10.9.9.9"


def _fake_socket(recv_results):
    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.recvfrom.side_effect = list(recv_results)
    return fake


class TestSyncSourceFiltering:
    def test_sync_send_recv_ignores_foreign_source(self):
        """A stray datagram from another host on the LAN must be discarded;
        the correct response from the target host is returned."""
        fake = _fake_socket(
            [
                (b"stray", (FOREIGN, 4000)),
                (b"good", (HOST, 4000)),
            ]
        )
        with patch("blauberg_vento.transport.socket.socket", return_value=fake):
            result = VentoTransport(timeout=0.05).send_recv(HOST, b"packet")
        assert result == b"good"

    def test_sync_send_recv_timeout_when_only_foreign_source(self):
        """If every incoming datagram comes from the wrong host, the call
        must end in VentoTimeoutError, never return foreign data."""
        fake = _fake_socket([(b"stray", (FOREIGN, 4000))] * 5 + [TimeoutError()])
        with patch("blauberg_vento.transport.socket.socket", return_value=fake):
            with pytest.raises(VentoTimeoutError):
                VentoTransport(timeout=0.05).send_recv(HOST, b"packet")


class TestAsyncSourceFiltering:
    def test_protocol_ignores_foreign_source(self):
        loop = asyncio.new_event_loop()
        try:
            future = loop.create_future()
            proto = _SingleResponseProtocol(future, expected_host=HOST)
            proto.datagram_received(b"stray", (FOREIGN, 4000))
            assert not future.done()
        finally:
            loop.close()

    def test_protocol_resolves_matching_source(self):
        loop = asyncio.new_event_loop()
        try:
            future = loop.create_future()
            proto = _SingleResponseProtocol(future, expected_host=HOST)
            addr = (HOST, 4000)
            proto.datagram_received(b"good", addr)
            assert future.done()
            assert future.result() == (b"good", addr)
        finally:
            loop.close()

    def test_protocol_without_expected_host_accepts_any_source(self):
        """Backward compatibility: with no expected host the first datagram
        resolves the future, as before."""
        loop = asyncio.new_event_loop()
        try:
            future = loop.create_future()
            proto = _SingleResponseProtocol(future)
            addr = (FOREIGN, 4000)
            proto.datagram_received(b"any", addr)
            assert future.done()
            assert future.result() == (b"any", addr)
        finally:
            loop.close()

    @pytest.mark.asyncio
    async def test_async_send_recv_end_to_end_matching_source(self):
        """End-to-end: a local responder answers from 127.0.0.1 (the target
        host), so the source filter lets the datagram through."""
        class Responder(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                self.transport.sendto(b"pong", addr)

        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(Responder, local_addr=("127.0.0.1", 0))
        port = transport.get_extra_info("sockname")[1]
        try:
            result = await AsyncVentoTransport(timeout=1.0).send_recv("127.0.0.1", b"ping", port)
            assert result == b"pong"
        finally:
            transport.close()
